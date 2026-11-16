from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from qiskit.providers.fake_provider import GenericBackendV2
from qiskit_ibm_runtime.options import SamplerOptions

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

    def test_noisy_aer_exports_real_results(self):
        code, files = self.run_smoke(["--qaoa-backend", "aer", "--aer-noise", "depolarizing"])
        self.assertEqual(code, 0)
        result = json.loads(files["result.json"])
        manifest = json.loads(files["run.json"])
        self.assertEqual(result["qubits"], 7)
        self.assertEqual(result["optimizer"], "COBYLA")
        self.assertGreater(result["evaluations"], 0)
        self.assertLessEqual(result["evaluations"], 30)
        self.assertEqual(result["training_shots"], 1024 * result["evaluations"])
        self.assertEqual(sum(result["counts"].values()), 256)
        self.assertEqual(result["parameter_training"], "noisy Aer simulation")
        self.assertEqual(manifest["dataset"]["columns"], ["Rain", "WetGrass"])
        self.assertEqual(manifest["dataset"]["rows"], 100)
        self.assertEqual(manifest["max_ibm_jobs"], 0)
        self.assertTrue(manifest["source_sha256"])
        self.assertTrue(manifest["versions"])
        self.assertIn("WetGrass_smoke.txt", files)

    def check_ibm(self, fail=False):
        backend = GenericBackendV2(7, basis_gates=["id", "rz", "sx", "x", "cx"], seed=42)
        with patch("qiskit_ibm_runtime.QiskitRuntimeService") as service, \
             patch("qiskit_ibm_runtime.SamplerV2") as sampler:
            service.return_value.backend.return_value = backend
            job = sampler.return_value.run.return_value
            job.job_id.return_value = "local-test-job"
            job.result.return_value[0].data.meas.get_counts.return_value = {"0000000": 256}
            if fail:
                job.result.side_effect = RuntimeError("Retrieval failed: " + self.secret)
            code, files = self.run_smoke([
                "--ibm-backend", backend.name, "--ibm-instance", "test-instance",
                "--ibm-api-key-file", str(self.key)])
            self.assertEqual(service.call_args.kwargs,
                             {"channel": "ibm_quantum_platform", "token": self.secret, "instance": "test-instance"})
            service.save_account.assert_not_called()
            sampler.return_value.run.assert_called_once()
            self.assertEqual(sampler.return_value.run.call_args.kwargs["shots"], 256)
            self.assertEqual(SamplerOptions(**sampler.call_args.kwargs["options"]).max_execution_time, 60)
        result = json.loads(files["result.json"])
        manifest = json.loads(files["run.json"])
        self.assertEqual(result["execution"]["job_id"], "local-test-job")
        self.assertEqual(code, 1 if fail else 0)
        self.assertEqual(manifest["status"], "failed" if fail else "completed")
        if fail:
            self.assertEqual(result["status"], "submitted")
            self.assertIn("[REDACTED]", manifest["error"])

    def test_ibm_key_file_and_single_job_budget(self):
        self.check_ibm()

    def test_ibm_retrieval_failure_preserves_job_id(self):
        self.check_ibm(fail=True)


if __name__ == "__main__":
    unittest.main()
