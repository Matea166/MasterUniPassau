import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bnsl-qa"))

try:
    import qiskit_aer
except ImportError:
    qiskit_aer = None

from bnslqa.solvers import qaoa_solver as qaoa


class QaoaMappingTests(unittest.TestCase):
    def test_ising_energies_match_every_binary_assignment(self):
        Q = np.array([[-3, 2, -1], [4, 0.5, 3], [2, -5, -2.]])
        linear, pairs, offset = qaoa.ising_coefficients(Q)
        for values in itertools.product((0, 1), repeat=3):
            bits = np.array(values)
            spins = 1 - 2 * bits
            self.assertAlmostEqual(bits @ Q @ bits, offset + linear @ spins + spins @ pairs @ spins)

    def test_qiskit_bit_order_maps_to_original_variables(self):
        np.testing.assert_array_equal(qaoa.sample_bits("1001", 4), [1, 0, 0, 1])
        np.testing.assert_array_equal(qaoa.sample_bits("001", 3), [1, 0, 0])
        with self.assertRaises(ValueError):
            qaoa.sample_bits("001", 4)

    def test_graph_filter_rejects_cycles_and_excess_parents(self):
        indices = [("d", 0, 1), ("d", 1, 2), ("d", 2, 0)]
        self.assertFalse(qaoa.graph_is_valid([1, 1, 1], indices, 3))
        self.assertTrue(qaoa.graph_is_valid([1, 1, 0], indices, 3))
        self.assertFalse(qaoa.graph_is_valid([1, 1, 1], [("d", i, 3) for i in range(3)], 4))


@unittest.skipIf(qiskit_aer is None, "Qiskit Aer is not installed")
class QaoaExecutionTests(unittest.TestCase):
    def test_cost_circuit_phases_match_original_qubo(self):
        from qiskit.quantum_info import Statevector

        Q = np.array([[-3, 2, -1], [4, 0.5, 3], [2, -5, -2.]])
        circuit, angles, scale, _ = qaoa.build_circuit(Q)
        circuit = circuit.remove_final_measurements(inplace=False)
        state = Statevector(circuit.assign_parameters({angles[0]: 0.71, angles[1]: 0})).data
        for i in range(8):
            bits = qaoa.sample_bits(format(i, "03b"), 3)
            expected = np.exp(-1j * 0.71 * (bits @ Q @ bits) / scale)
            np.testing.assert_allclose(state[i] / state[0], expected, atol=1e-12)

    def test_aer_sampling_is_seeded_and_uses_minimum_energy(self):
        Q = np.array([[-1., 2], [0, -0.5]])
        first = qaoa.solve(Q, shots=64, maxiter=5, seed=7)
        second = qaoa.solve(Q, shots=64, maxiter=5, seed=7)
        self.assertEqual(first["counts"], second["counts"])
        self.assertEqual(first["history"], second["history"])
        energies = [float((bits := qaoa.sample_bits(key, 2)) @ Q @ bits) for key in first["counts"]]
        self.assertEqual(first["best_energy"], min(energies))
        self.assertEqual(first["final_shots"], 64)

    def test_no_valid_sample_is_not_a_zero_estimate(self):
        result = qaoa.solve([[-1.]], shots=8, maxiter=4, accept_sample=lambda bits: False)
        self.assertEqual(result["status"], "no_valid_graph")
        self.assertIsNone(result["best_bits"])
        self.assertIsNone(result["best_energy"])

    def test_qubit_limit_stops_before_simulation(self):
        with self.assertRaisesRegex(ValueError, "needs 3 qubits"):
            qaoa.solve(np.eye(3), max_qubits=2)

    def test_ibm_adapter_transpiles_and_records_job_before_result(self):
        try:
            import qiskit_ibm_runtime
        except ImportError:
            self.skipTest("Qiskit Runtime is not installed")
        from qiskit import QuantumCircuit
        from qiskit.providers.fake_provider import GenericBackendV2
        from qiskit_aer.primitives import SamplerV2

        circuit = QuantumCircuit(2)
        circuit.x(0)
        circuit.measure_all()
        backend = GenericBackendV2(3, seed=42)
        events = []

        def run(circuits, shots):
            local = SamplerV2(seed=42).run(circuits, shots=shots)
            def result():
                events.append("result")
                return local.result()
            return Mock(job_id=lambda: "offline-test", result=result)

        service = Mock()
        service.backend.return_value = backend
        with patch.object(qiskit_ibm_runtime, "QiskitRuntimeService", return_value=service), \
                patch.object(qiskit_ibm_runtime, "SamplerV2", return_value=Mock(run=run)):
            counts, metadata = qaoa.sample_ibm(circuit, "test_backend", 16, 42,
                                             lambda job: events.append("submitted"))
        self.assertEqual(events, ["submitted", "result"])
        self.assertEqual(counts, {"01": 16})
        self.assertEqual(metadata["job_id"], "offline-test")
        self.assertEqual(metadata["compiled_qubits"], 3)
        service.backend.assert_called_once_with("test_backend")

    def test_ibm_sampling_receives_fixed_aer_trained_parameters(self):
        try:
            import qiskit_ibm_runtime
        except ImportError:
            self.skipTest("Qiskit Runtime is not installed")
        submitted = Mock()

        def sample(circuit, backend, shots, seed, on_submit):
            self.assertEqual(circuit.num_parameters, 0)
            self.assertEqual(backend, "test_backend")
            metadata = {"backend": backend, "job_id": "offline-test"}
            on_submit(metadata)
            return {"01": shots}, metadata

        with patch.object(qaoa, "sample_ibm", side_effect=sample):
            result = qaoa.solve([[-1., 2], [0, -0.5]], shots=16, maxiter=4,
                                ibm_backend="test_backend", on_submit=submitted)
        pending = submitted.call_args.args[0]
        self.assertEqual(pending["angles"], result["angles"])
        self.assertEqual(pending["execution"]["job_id"], "offline-test")
        self.assertEqual(result["best_bits"], [1, 0])
        self.assertEqual(result["training_shots"], 16 * result["evaluations"])

    def test_cli_runs_a_real_bn_qubo_and_saves_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "two_variables.txt"
            source.write_text("2 2 2\nsmall\n0 1\n0 0\n0 0\n1 1\n1 1\n")
            output = Path(directory) / "result.json"
            env = dict(os.environ, PYTHONPATH=str(ROOT / "bnsl-qa"))
            command = [sys.executable, "-m", "bnslqa", "solve", str(source), "QAOA",
                       "--shots", "64", "--maxiter", "5", "--qaoa-output", str(output)]
            plan = subprocess.run(command + ["--dry-run"], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertEqual(json.loads(plan.stdout)["qubits"], 7)
            self.assertFalse(output.exists())
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(output.read_text())
            self.assertEqual(result["qubits"], 7)
            self.assertEqual(len(result["variable_order"]), 7)
            self.assertIn("dataset_sha256", result)
            self.assertEqual(result["status"], "completed")
            self.assertIn("Solution adjacency matrix:", run.stdout)

    def test_dispatch_fits_sampled_graphs_and_exports_cardinalities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "small.txt"
            source.write_text("2 2 2\nsmall\n0 1\n0 0\n0 0\n1 1\n1 1\n")
            shutil.copy(ROOT / "bnsl-qa/dispatch.sh", root)
            estimator = root / "estimate.py"
            estimator.write_text(
                "import ast,sys\nfrom pathlib import Path\nimport pandas as pd\n"
                "from pgmpy.inference import VariableElimination\n"
                "from cardinality_estimation.cardinality_estimation_WetGrass import fit_model, estimate_probability\n"
                "data=pd.DataFrame({'a':[0,0,1,1],'b':[0,0,1,1]})\n"
                "model=fit_model(data,ast.literal_eval(sys.argv[1]))\n"
                "estimate=4*estimate_probability(VariableElimination(model),{'a':0,'b':0})\n"
                "pd.DataFrame({'query_sql':['SELECT * FROM t WHERE a=0 AND b=0;'],"
                "'estimated_cardinality':[estimate]}).to_csv("
                "Path(sys.argv[2])/('graph_'+sys.argv[3]+'_cardinality.csv'),index=False)\n")
            env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + str(ROOT / "bnsl-qa"),
                       PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
                       DATASET_TXT=str(source), SOLVER="QAOA", TRIALS="2", READS="32",
                       CE_SCRIPT=str(estimator), QAOA_MAXITER="4", QAOA_SEED="7",
                       QAOA_RESULTS_DIR=str(root / "metadata"))
            run = subprocess.run(["bash", "dispatch.sh"], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("DISPATCH_FINAL_CSV=", run.stdout)
            for i in (1, 2):
                result = json.loads((root / f"metadata/trial_{i}.json").read_text())
                self.assertEqual(result["seed"], 6 + i)
                self.assertEqual(result["shots_per_evaluation"], 32)
            exported = next((root / "dispatch_output/results").glob("*.csv"))
            self.assertIn("Graph_1.png", exported.read_text())
            self.assertIn("a=0 AND b=0", exported.read_text())


if __name__ == "__main__":
    unittest.main()
