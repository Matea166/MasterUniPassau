from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from qiskit.providers.fake_provider import GenericBackendV2
from qiskit_ibm_runtime.exceptions import IBMRuntimeError

from scripts import run_ibm_smoke as smoke


class IbmSmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.secret = "LOCAL-TEST-KEY-NOT-FOR-EXPORT"
        self.key = self.root / "ibm_api_key.txt"
        self.key.write_text(self.secret + "\n")

    def run_smoke(self, arguments):
        output = self.root / "results"
        with patch.object(sys, "argv", ["run_ibm_smoke.py", "--output-dir", str(output)] + arguments), \
             redirect_stdout(io.StringIO()) as console:
            code = smoke.main()
        with ZipFile(next(output.glob("*.zip"))) as bundle:
            self.assertIsNone(bundle.testzip())
            files = {Path(name).name: bundle.read(name) for name in bundle.namelist()}
        self.assertNotIn(self.secret, console.getvalue())
        for data in files.values():
            self.assertNotIn(self.secret.encode(), data)
        return code, files

    def test_ideal_aer_exports_real_results(self):
        with patch("qiskit_ibm_runtime.QiskitRuntimeService") as service:
            code, files = self.run_smoke(["--qaoa-backend", "aer"])
            service.assert_not_called()
        self.assertEqual(code, 0)
        result = json.loads(files["result.json"])
        manifest = json.loads(files["run.json"])
        self.assertEqual(result["qubits"], 7)
        self.assertEqual(manifest["qubits"], len(result["variable_order"]))
        self.assertEqual(result["optimizer"], "COBYLA")
        self.assertGreater(result["evaluations"], 0)
        self.assertIsNone(result["max_evaluations"])
        self.assertEqual(result["training_shots"], 1024 * result["evaluations"])
        self.assertEqual(sum(result["counts"].values()), 1024)
        self.assertEqual(result["parameter_training"], "ideal Aer simulation")
        self.assertEqual(result["aer_noise"], {"model": "none"})
        self.assertEqual(manifest["dataset"]["columns"], ["Rain", "WetGrass"])
        self.assertEqual(manifest["dataset"]["rows"], 10)
        self.assertEqual(len(files["WetGrass_smoke.txt"].decode().splitlines()) - 3, 10)
        self.assertEqual(manifest["max_ibm_jobs"], 0)
        self.assertTrue(manifest["source_sha256"])
        self.assertTrue(manifest["versions"])
        self.assertIn("WetGrass_smoke.txt", files)

    def test_explicit_optimizer_budget_remains_available(self):
        result = smoke.qaoa_solver.solve([[1.0]], shots=64, maxiter=6)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["max_evaluations"], 6)
        self.assertGreater(result["evaluations"], 0)
        self.assertLessEqual(result["evaluations"], 6)
        self.assertEqual(sum(result["counts"].values()), 64)

    def test_qaoa_cli_rejects_removed_noise_option(self):
        run = subprocess.run(
            [sys.executable, "-m", "bnslqa", "solve", "unused", "QAOA",
             "--aer-noise", "depolarizing"],
            cwd=smoke.ROOT, capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, 2)
        self.assertIn("unrecognized arguments: --aer-noise", run.stderr)

    def test_cli_rejects_invalid_minimum_even_when_valid_sample_is_available(self):
        with redirect_stdout(io.StringIO()):
            dataset, _ = smoke.prepare_dataset(self.root)
        output = self.root / "failed_result.json"
        program = (
            "from bnslqa.solvers import qaoa_solver\n"
            "qaoa_solver.sample_ibm = lambda *args, **kwargs: "
            "({'0000011': 1, '0000001': 1023}, {'backend': 'local-test'})\n"
            "from bnslqa.__main__ import main\n"
            "main()\n"
        )
        run = subprocess.run(
            [sys.executable, "-c", program, "solve", str(dataset), "QAOA",
             "--qaoa-backend", "ibm", "--qaoa-output", str(output)],
            cwd=smoke.ROOT, capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, 3)
        self.assertIn("Minimum-energy sample failed graph validation", run.stderr)
        self.assertNotIn("Solution adjacency matrix:", run.stdout)
        result = json.loads(output.read_text())
        self.assertEqual(result["status"], "no_valid_graph")
        self.assertEqual(result["counts"], {"0000011": 1, "0000001": 1023})
        self.assertIsNone(result["adjacency_matrix"])

    def test_smoke_preserves_failed_run_without_a_valid_graph(self):
        with patch.object(smoke.qaoa_solver, "sample_ibm", return_value=(
            {"0000011": 1024}, {"backend": "local-test"}
        )):
            code, files = self.run_smoke([])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(files["run.json"])["status"], "failed")
        result = json.loads(files["result.json"])
        self.assertEqual(result["status"], "no_valid_graph")
        self.assertEqual(result["counts"], {"0000011": 1024})

    def check_ibm(self, fail=False, automatic=False, metrics_fail=False, usage_fail=False,
                  invalid_timestamps=False):
        backend = GenericBackendV2(7, basis_gates=["id", "rz", "sx", "x", "cx"], seed=42)
        with patch("qiskit_ibm_runtime.QiskitRuntimeService") as service, \
             patch("qiskit_ibm_runtime.SamplerV2") as sampler:
            service.return_value.backend.return_value = backend
            service.return_value.least_busy.return_value = backend
            job = sampler.return_value.run.return_value
            job.job_id.return_value = "local-test-job"
            job.result.return_value[0].data.meas.get_counts.return_value = {"0000001": 1024}
            job.metrics.return_value = {
                "timestamps": {"created": "2026-11-22T10:00:00Z", "finished": "2026-11-22T10:00:25Z"},
                "usage": {"quantum_seconds": 1.25},
            }
            job.usage.return_value = 1.25
            if invalid_timestamps:
                job.metrics.return_value["timestamps"]["finished"] = "not-a-date"
            if metrics_fail:
                job.metrics.side_effect = IBMRuntimeError("Metrics unavailable")
            if usage_fail:
                job.usage.side_effect = IBMRuntimeError("Usage unavailable")
            if fail:
                job.result.side_effect = RuntimeError("Retrieval failed: " + self.secret)
            arguments = ["--ibm-instance", "test-instance", "--ibm-api-key-file", str(self.key)]
            if not automatic:
                arguments.extend(["--ibm-backend", backend.name])
            code, files = self.run_smoke(arguments)
            self.assertEqual(service.call_args.kwargs,
                             {"channel": "ibm_quantum_platform", "token": self.secret, "instance": "test-instance"})
            service.save_account.assert_not_called()
            sampler.return_value.run.assert_called_once()
            self.assertEqual(sampler.return_value.run.call_args.kwargs["shots"], 1024)
            if automatic:
                service.return_value.least_busy.assert_called_once_with(
                    operational=True, simulator=False, min_num_qubits=7)
        result = json.loads(files["result.json"])
        manifest = json.loads(files["run.json"])
        self.assertEqual(result["execution"]["job_id"], "local-test-job")
        self.assertEqual(code, 1 if fail else 0)
        self.assertEqual(manifest["status"], "failed" if fail else "completed")
        if not fail:
            self.assertEqual(result["adjacency_matrix"], [[0, 1], [0, 0]])
            matrix_lines = files["run.log"].decode().split("Solution adjacency matrix:\n", 1)[1].splitlines()[:2]
            self.assertEqual([json.loads(line) for line in matrix_lines], result["adjacency_matrix"])
        if not fail and not metrics_fail and not invalid_timestamps:
            self.assertEqual(result["execution"]["elapsed_seconds"], 25.0)
        if not fail and not usage_fail:
            self.assertEqual(result["execution"]["qpu_seconds"], 1.25)
            self.assertIn(b"QPU usage time: 1.2500 s", files["run.log"])
        if metrics_fail:
            self.assertEqual(result["execution"]["metrics_status"], "unavailable")
        if usage_fail:
            self.assertEqual(result["execution"]["usage_status"], "unavailable")
        if invalid_timestamps:
            self.assertEqual(result["execution"]["timestamps_status"], "invalid")
        if fail:
            self.assertEqual(result["status"], "submitted")
            self.assertIn("[REDACTED]", manifest["error"])

    def test_ibm_key_file_and_single_job_budget(self):
        self.check_ibm()

    def test_ibm_selects_a_suitable_backend(self):
        self.check_ibm(automatic=True)

    def test_ibm_keeps_results_when_metrics_are_unavailable(self):
        self.check_ibm(metrics_fail=True)

    def test_ibm_keeps_results_when_usage_is_unavailable(self):
        self.check_ibm(usage_fail=True)

    def test_ibm_keeps_results_when_timestamps_are_invalid(self):
        self.check_ibm(invalid_timestamps=True)

    def test_ibm_uses_saved_account(self):
        backend = GenericBackendV2(7, basis_gates=["id", "rz", "sx", "x", "cx"], seed=42)
        with patch("qiskit_ibm_runtime.QiskitRuntimeService") as service, \
             patch("qiskit_ibm_runtime.SamplerV2") as sampler:
            service.return_value.least_busy.return_value = backend
            job = sampler.return_value.run.return_value
            job.job_id.return_value = "local-test-job"
            job.result.return_value[0].data.meas.get_counts.return_value = {"0000000": 1024}
            code, files = self.run_smoke([])
            self.assertEqual(service.call_args.kwargs, {})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(files["result.json"])["status"], "completed")

    def test_ibm_retrieval_failure_preserves_job_id(self):
        self.check_ibm(fail=True)


if __name__ == "__main__":
    unittest.main()
