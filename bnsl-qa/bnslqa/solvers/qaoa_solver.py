import hashlib
import json
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter, time_ns

import networkx as nx
import numpy as np


class InvalidGraphError(RuntimeError):
    pass


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


def sample_ibm(circuit, backend_name, shots, seed, on_submit,
               api_key_file=None, instance=None):
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    account = {"instance": instance} if instance else {}
    if api_key_file:
        token = Path(api_key_file).read_text().strip()
        if not token:
            raise ValueError("The IBM API key file is empty.")
        account.update(channel="ibm_quantum_platform", token=token)
    service = QiskitRuntimeService(**account)
    if backend_name == "auto":
        backend = service.least_busy(operational=True, simulator=False,
                                     min_num_qubits=circuit.num_qubits)
    else:
        backend = service.backend(backend_name)
    if circuit.num_qubits > backend.num_qubits:
        raise ValueError("The selected IBM backend has too few qubits.")
    pm = generate_preset_pass_manager(backend=backend, optimization_level=1,
                                      seed_transpiler=seed)
    isa_qc = pm.run(circuit)
    sampler = SamplerV2(mode=backend)
    job = sampler.run([isa_qc], shots=shots)
    metadata = {"backend": backend.name, "job_id": job.job_id(),
                "compiled_qubits": isa_qc.num_qubits, "depth": isa_qc.depth(),
                "two_qubit_gates": sum(item.operation.num_qubits == 2 for item in isa_qc.data)}
    if on_submit:
        on_submit(metadata)
    result = job.result()
    counts = result[0].data.meas.get_counts()

    # Timing is optional: a metrics failure should not discard the counts.
    try:
        timestamps = job.metrics().get("timestamps") or {}
        metadata["timestamps"] = {key: str(timestamps[key]) for key in
                                  ("created", "running", "finished") if timestamps.get(key)}
        if timestamps.get("created") and timestamps.get("finished"):
            created = datetime.fromisoformat(str(timestamps["created"]).replace("Z", "+00:00"))
            finished = datetime.fromisoformat(str(timestamps["finished"]).replace("Z", "+00:00"))
            metadata["elapsed_seconds"] = (finished - created).total_seconds()
    except (TypeError, ValueError):
        metadata["timestamps_status"] = "invalid"
    except Exception:
        metadata["metrics_status"] = "unavailable"
    try:
        qpu_time = job.usage()
        if isinstance(qpu_time, (int, float)):
            metadata["qpu_seconds"] = qpu_time
            print(f"QPU usage time: {qpu_time:.4f} s")
    except Exception:
        metadata["usage_status"] = "unavailable"
    if "elapsed_seconds" in metadata:
        print(f"Total job time: {metadata['elapsed_seconds']:.4f} s")
    return counts, metadata


def solve(Q, reps=1, shots=1024, maxiter=None, seed=42,
          accept_sample=None, ibm_backend=None, on_submit=None, final_shots=None,
          ibm_api_key_file=None, ibm_instance=None):
    from qiskit import transpile
    from qiskit_aer import AerSimulator
    from qiskit_aer.primitives import SamplerV2
    from scipy.optimize import minimize

    Q = np.asarray(Q, dtype=float)
    final_shots = shots if final_shots is None else final_shots
    if min(reps, shots, final_shots) < 1:
        raise ValueError("Repetitions and shots must be positive.")
    if maxiter is not None and maxiter < 2 * reps + 2:
        raise ValueError("COBYLA needs at least 2 * reps + 2 evaluations.")
    circuit, angles, scale, offset = build_circuit(Q, reps)
    noise_settings = {"model": "none"}
    training = "ideal Aer simulation"
    backend_options = {"method": "statevector"}
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
    options = {"maxiter": maxiter} if maxiter is not None else {}
    optimization = minimize(objective, initial, method="COBYLA", options=options)
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
        counts, backend_info = sample_ibm(logical, ibm_backend, final_shots, seed, submitted,
                                          api_key_file=ibm_api_key_file, instance=ibm_instance)
    else:
        counts = sampler.run([bound], shots=final_shots).result()[0].data.meas.get_counts()
    candidates = []
    for bitstring, count in counts.items():
        bits = sample_bits(bitstring, len(Q))
        candidates.append((float(bits @ Q @ bits), -count, bitstring, bits.tolist()))
    selected = min(candidates) if candidates else None
    if selected is not None and accept_sample is not None and not accept_sample(np.array(selected[3], dtype=int)):
        selected = None
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
    noise_settings = {"model": "none"}
    plan = {"dataset": name, "attributes": n, "qubits": width,
            "statevector_gib": 16 * 2 ** width / 1024 ** 3,
            "shots_per_evaluation": args.shots,
            "final_shots": args.shots if args.final_shots is None else args.final_shots,
            "parameter_training": "ideal Aer simulation",
            "aer_noise": noise_settings, "backend": args.qaoa_backend}
    if args.qaoa_backend == "ibm":
        plan["ibm_backend"] = args.ibm_backend or "auto"
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return
    if args.qaoa_backend == "aer" and args.ibm_backend:
        raise ValueError("--ibm-backend requires --qaoa-backend ibm.")
    if args.qaoa_backend == "aer" and (args.ibm_api_key_file or args.ibm_instance):
        raise ValueError("IBM account options require --qaoa-backend ibm.")
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

    result = solve(Q, reps=args.reps, shots=args.shots, maxiter=getattr(args, "maxiter", None),
                   seed=args.seed,
                   accept_sample=lambda bits: graph_is_valid(bits, indices, n),
                   ibm_backend=(args.ibm_backend or "auto") if args.qaoa_backend == "ibm" else None,
                   on_submit=on_submit, final_shots=args.final_shots,
                   ibm_api_key_file=args.ibm_api_key_file, ibm_instance=args.ibm_instance)
    result["adjacency_matrix"] = None
    if result["best_bits"] is not None:
        adjacency = np.zeros((n, n), dtype=int)
        for (kind, parent, child), bit in zip(indices, result["best_bits"]):
            if kind == "d":
                adjacency[parent, child] = bit
        result["adjacency_matrix"] = adjacency.tolist()
    result.update(metadata)
    write_result(output, result)
    print(f"QAOA result: {output}")
    if result["best_bits"] is None:
        raise InvalidGraphError("Minimum-energy sample failed graph validation.")
    print("Solution adjacency matrix:")
    printAdjMat(n, torch.tensor(result["best_bits"]))
    print(f"QUBO energy: {result['best_energy']}")
