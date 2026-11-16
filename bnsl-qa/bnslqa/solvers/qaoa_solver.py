import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from time import perf_counter, time_ns

import networkx as nx
import numpy as np


def ising_coefficients(Q):
    Q = np.asarray(Q, dtype=float)
    if Q.ndim != 2 or Q.shape[0] != Q.shape[1] or not Q.size or not np.isfinite(Q).all():
        raise ValueError("Q must be a nonempty, finite square matrix.")
    pairs = np.triu(Q + Q.T, 1) / 4
    linear = -np.diag(Q) / 2 - pairs.sum(axis=0) - pairs.sum(axis=1)
    offset = np.trace(Q) / 2 + pairs.sum()
    return linear, pairs, float(offset)


def build_circuit(Q, reps=1):
    from qiskit.circuit.library import qaoa_ansatz
    from qiskit.quantum_info import SparsePauliOp

    linear, pairs, offset = ising_coefficients(Q)
    scale = float(max(np.max(np.abs(linear)), np.max(np.abs(pairs)))) or 1.0
    terms = [("Z", [i], coefficient / scale) for i, coefficient in enumerate(linear) if coefficient]
    terms += [("ZZ", [int(i), int(j)], pairs[i, j] / scale) for i, j in zip(*np.nonzero(pairs))]
    operator = SparsePauliOp.from_sparse_list(terms or [("Z", [0], 0.0)], num_qubits=len(linear))
    circuit = qaoa_ansatz(operator, reps=reps)
    parameters = list(circuit.parameters)
    angles = parameters[reps:] + parameters[:reps]
    circuit.measure_all()
    return circuit, angles, scale, offset


def sample_bits(bitstring, width):
    bits = bitstring.replace(" ", "")
    if len(bits) != width or set(bits) - {"0", "1"}:
        raise ValueError("Measured bitstring does not match the QUBO width.")
    return np.array([int(bit) for bit in bits[::-1]], dtype=int)


def graph_is_valid(bits, indices, n):
    graph = nx.DiGraph()
    graph.add_nodes_from(range(n))
    graph.add_edges_from((index[1], index[2]) for index, bit in zip(indices, bits)
                         if index[0] == "d" and bit)
    return nx.is_directed_acyclic_graph(graph) and all(d <= 2 for _, d in graph.in_degree())


def write_result(path, result):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")


def aer_noise_model(mode):
    if mode == "none":
        return None, {"model": "none"}
    if mode != "depolarizing":
        raise ValueError("Aer noise must be none or depolarizing.")
    from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error

    settings = {"model": "depolarizing", "one_qubit_error": 0.001,
                "two_qubit_error": 0.01, "readout_error": 0.02,
                "basis_gates": ["rz", "sx", "x", "cx"], "device_calibrated": False}
    model = NoiseModel(basis_gates=settings["basis_gates"])
    model.add_all_qubit_quantum_error(depolarizing_error(settings["one_qubit_error"], 1),
                                      ["sx", "x"])
    model.add_all_qubit_quantum_error(depolarizing_error(settings["two_qubit_error"], 2), ["cx"])
    p = settings["readout_error"]
    model.add_all_qubit_readout_error(ReadoutError([[1 - p, p], [p, 1 - p]]))
    settings["noiseless_gates"] = ["rz"]
    return model, settings


def sample_ibm(circuit, backend_name, shots, seed, on_submit):
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    backend = QiskitRuntimeService().backend(backend_name)
    if circuit.num_qubits > backend.num_qubits:
        raise ValueError("The selected IBM backend has too few qubits.")
    manager = generate_preset_pass_manager(backend=backend, optimization_level=3,
                                           seed_transpiler=seed)
    compiled = manager.run(circuit)
    job = SamplerV2(mode=backend).run([compiled], shots=shots)
    metadata = {"backend": backend.name, "job_id": job.job_id(),
                "compiled_qubits": compiled.num_qubits, "depth": compiled.depth(),
                "two_qubit_gates": sum(item.operation.num_qubits == 2 for item in compiled.data)}
    if on_submit:
        on_submit(metadata)
    result = job.result()[0]
    return result.data.meas.get_counts(), metadata


def solve(Q, reps=1, shots=1024, maxiter=30, seed=42, max_qubits=20,
          accept_sample=None, ibm_backend=None, on_submit=None, aer_noise="none", final_shots=None):
    from qiskit import transpile
    from qiskit_aer import AerSimulator
    from qiskit_aer.primitives import SamplerV2
    from scipy.optimize import minimize

    Q = np.asarray(Q, dtype=float)
    final_shots = shots if final_shots is None else final_shots
    if min(reps, shots, final_shots, maxiter, max_qubits) < 1:
        raise ValueError("Repetitions, shots, evaluations and qubit limit must be positive.")
    if maxiter < 2 * reps + 2:
        raise ValueError("COBYLA needs at least 2 * reps + 2 evaluations.")
    if len(Q) > max_qubits:
        raise ValueError(f"This QUBO needs {len(Q)} qubits; the simulator limit is {max_qubits}.")
    circuit, angles, scale, offset = build_circuit(Q, reps)
    noise_model, noise_settings = aer_noise_model(aer_noise)
    training = "ideal Aer simulation" if noise_model is None else "noisy Aer simulation"
    backend_options = {"method": "statevector"}
    if noise_model is not None:
        backend_options.update(noise_model=noise_model, basis_gates=noise_settings["basis_gates"])
    simulator = AerSimulator(**backend_options)
    compiled = transpile(circuit, simulator, optimization_level=1, seed_transpiler=seed)
    sampler = SamplerV2(default_shots=shots, seed=seed,
                        options={"backend_options": backend_options})
    history = []
    best = {"value": float("inf"), "angles": None}
    started = perf_counter()

    def objective(values):
        bound = compiled.assign_parameters(dict(zip(angles, values)))
        counts = sampler.run([bound], shots=shots).result()[0].data.meas.get_counts()
        energy = sum(count * float((bits := sample_bits(key, len(Q))) @ Q @ bits)
                     for key, count in counts.items()) / sum(counts.values())
        history.append({"mean_energy": energy, "angles": values.tolist()})
        if energy < best["value"]:
            best.update(value=energy, angles=values.copy())
        return (energy - offset) / scale

    rng = np.random.default_rng(seed)
    initial = np.concatenate([rng.uniform(0, 2 * np.pi, reps), rng.uniform(0, np.pi, reps)])
    optimization = minimize(objective, initial, method="COBYLA", options={"maxiter": maxiter})
    bound = compiled.assign_parameters(dict(zip(angles, best["angles"])))
    training_seconds = perf_counter() - started
    backend_info = {"backend": "aer_simulator_statevector", "depth": bound.depth(),
                    "two_qubit_gates": sum(item.operation.num_qubits == 2 for item in bound.data)}
    if ibm_backend:
        logical = circuit.assign_parameters(dict(zip(angles, best["angles"])))
        def submitted(job):
            if on_submit:
                on_submit({"execution": job, "angles": best["angles"].tolist(),
                           "parameter_order": [parameter.name for parameter in angles],
                           "seed": seed, "reps": reps, "shots_per_evaluation": shots,
                           "training_shots": shots * len(history), "final_shots": final_shots,
                           "history": history, "parameter_training": training,
                           "aer_noise": noise_settings})
        counts, backend_info = sample_ibm(logical, ibm_backend, final_shots, seed, submitted)
    else:
        counts = sampler.run([bound], shots=final_shots).result()[0].data.meas.get_counts()
    candidates = []
    for bitstring, count in counts.items():
        bits = sample_bits(bitstring, len(Q))
        if accept_sample is None or accept_sample(bits):
            candidates.append((float(bits @ Q @ bits), -count, bitstring, bits.tolist()))
    selected = min(candidates) if candidates else None
    packages = ["qiskit", "qiskit-aer", "numpy", "scipy"]
    if ibm_backend:
        packages.append("qiskit-ibm-runtime")
    return {"status": "completed" if selected else "no_valid_graph", "method": "QAOA",
            "parameter_training": training, "aer_noise": noise_settings, "execution": backend_info,
            "qubits": len(Q), "reps": reps, "shots_per_evaluation": shots,
            "training_shots": shots * len(history), "final_shots": sum(counts.values()),
            "seed": seed, "max_evaluations": maxiter,
            "optimizer": "COBYLA", "optimizer_success": bool(optimization.success),
            "optimizer_message": str(optimization.message), "evaluations": len(history),
            "angles": best["angles"].tolist(), "parameter_order": [parameter.name for parameter in angles],
            "training_mean_energy": best["value"],
            "ising_scale": scale, "ising_offset": offset, "history": history,
            "counts": counts, "best_bits": selected[3] if selected else None,
            "best_energy": selected[0] if selected else None,
            "training_seconds": training_seconds, "total_seconds": perf_counter() - started,
            "versions": {package: version(package) for package in packages}}


def main(args):
    from .qubo_matrix import calcQUBOMatrix
    from .solver_utils import getData, printAdjMat
    import torch

    examples, n, states, name, _ = getData(args.dataset)
    width = n * (n - 1) + 2 * n + n * (n - 1) // 2
    _, noise_settings = aer_noise_model(args.aer_noise)
    plan = {"dataset": name, "attributes": n, "qubits": width,
            "statevector_gib": 16 * 2 ** width / 1024 ** 3,
            "shots_per_evaluation": args.shots,
            "final_shots": args.shots if args.final_shots is None else args.final_shots,
            "parameter_training": "ideal Aer simulation" if args.aer_noise == "none" else "noisy Aer simulation",
            "aer_noise": noise_settings, "backend": args.qaoa_backend}
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return
    if width > args.max_qubits:
        raise ValueError(f"This QUBO needs {width} qubits. Use --dry-run to inspect resources; "
                         "increase --max-qubits only if the simulator has enough memory.")
    if args.qaoa_backend == "ibm" and not args.ibm_backend:
        raise ValueError("IBM execution requires an explicit --ibm-backend name.")
    if args.qaoa_backend == "aer" and args.ibm_backend:
        raise ValueError("--ibm-backend requires --qaoa-backend ibm.")
    Q, indices, _ = calcQUBOMatrix(examples, n, states)
    matrix = torch.tensor(Q)
    Q = matrix.numpy().astype(float)
    output = Path(args.qaoa_output) if args.qaoa_output else (
        Path(__file__).resolve().parents[3] / "results/qaoa" / f"run_{time_ns()}.json")
    metadata = {"dataset": name, "dataset_sha256": hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
                "qubo_sha256": hashlib.sha256(np.asarray(Q, dtype="<f8").tobytes()).hexdigest(),
                "qubo_coefficient_dtype": str(matrix.dtype), "variable_order": indices}

    def on_submit(job):
        write_result(output, dict(metadata, status="submitted", **job))
        print(f"IBM job submitted: {job['execution']['job_id']}", flush=True)

    result = solve(Q, reps=args.reps, shots=args.shots, maxiter=args.maxiter,
                   seed=args.seed, max_qubits=args.max_qubits,
                   accept_sample=lambda bits: graph_is_valid(bits, indices, n),
                   ibm_backend=args.ibm_backend if args.qaoa_backend == "ibm" else None,
                   on_submit=on_submit, aer_noise=args.aer_noise, final_shots=args.final_shots)
    result.update(metadata)
    write_result(output, result)
    print(f"QAOA result: {output}")
    if result["best_bits"] is None:
        print("No valid DAG sampled.")
        return
    print("Solution adjacency matrix:")
    printAdjMat(n, torch.tensor(result["best_bits"]))
    print(f"QUBO energy: {result['best_energy']}")
