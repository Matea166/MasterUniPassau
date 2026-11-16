import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import platform
import sys
from time import time_ns
from types import SimpleNamespace
import traceback
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bnsl-qa"))

from bnslqa.solvers import qaoa_solver


def prepare_dataset(output):
    from bnslqa.generators.generator import generateExpected

    problem = json.loads((ROOT / "bnsl-qa/problems/WetGrass.json").read_text())
    variables = problem["variables"]
    states = {name: len(variable["states"]) for name, variable in variables.items()}
    counts = {name: [0] * max(states.values()) for name in variables}
    data = io.StringIO()
    generateExpected(data, variables, problem["toporder"], states, 100, counts)
    columns = ["Rain", "WetGrass"]
    positions = [list(variables).index(name) for name in columns]
    rows = [[int(row.split()[i]) for i in positions] for row in data.getvalue().splitlines()]
    path = output / "WetGrass_smoke.txt"
    path.write_text("2 2 2\nWetGrass_smoke_Rain_WetGrass\n0 0\n" +
                    "".join(" ".join(map(str, row)) + "\n" for row in rows))
    return path, {"source": "bnsl-qa/problems/WetGrass.json", "columns": columns,
                  "rows": len(rows), "states": {name: variables[name]["states"] for name in columns}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qaoa-backend", choices=["aer", "ibm"], default="ibm")
    parser.add_argument("--ibm-backend", default=os.environ.get("IBM_BACKEND"))
    parser.add_argument("--ibm-instance", default=os.environ.get("IBM_INSTANCE"))
    parser.add_argument("--ibm-api-key-file", type=Path, default=Path("/run/secrets/ibm_api_key"))
    parser.add_argument("--aer-noise", choices=["none", "depolarizing"], default="none")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/ibm")
    args = parser.parse_args()
    ibm = args.qaoa_backend == "ibm"
    output = args.output_dir.resolve() / f"smoke_{time_ns()}"
    output.mkdir(parents=True)
    result_path = output / "result.json"
    log_path = output / "run.log"
    manifest = {"status": "running", "scenario": "WetGrass Rain/WetGrass projection",
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "qaoa_backend": args.qaoa_backend, "ibm_backend": args.ibm_backend if ibm else None,
                "qubits": 7, "reps": 1, "optimizer": "COBYLA", "max_evaluations": 30,
                "shots_per_evaluation": 1024, "final_shots": 256, "seed": 42,
                "aer_noise": args.aer_noise, "max_ibm_jobs": 1 if ibm else 0,
                "ibm_max_execution_time": 60 if ibm else None, "python": platform.python_version()}
    token = ""
    print(f"Running {args.qaoa_backend} smoke test. Results: {output}", flush=True)
    try:
        with log_path.open("w") as log, redirect_stdout(log), redirect_stderr(log):
            manifest["versions"] = {name: version(name) for name in
                                    ("qiskit", "qiskit-aer", "qiskit-ibm-runtime", "numpy", "scipy")}
            if ibm:
                if not args.ibm_backend or not args.ibm_instance:
                    raise ValueError("Set IBM_BACKEND and IBM_INSTANCE, or pass their command-line options.")
                token = args.ibm_api_key_file.read_text().strip()
                if not token:
                    raise ValueError("The IBM API key file is empty.")
            dataset, manifest["dataset"] = prepare_dataset(output)
            source_files = sorted((ROOT / "bnsl-qa/bnslqa").rglob("*.py"))
            source_files += [Path(__file__).resolve(), ROOT / "bnsl-qa/problems/WetGrass.json",
                             ROOT / "requirements.txt", ROOT / "docker-compose.quantum.yml",
                             ROOT / "docker/app/Dockerfile"]
            manifest["source_sha256"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                         for path in source_files}
            qaoa_solver.write_result(output / "run.json", manifest)
            qaoa_solver.main(SimpleNamespace(
                dataset=str(dataset), reps=1, shots=1024, final_shots=256, maxiter=30,
                seed=42, max_qubits=7, qaoa_backend=args.qaoa_backend,
                ibm_backend=args.ibm_backend if ibm else None,
                ibm_instance=args.ibm_instance if ibm else None,
                ibm_api_key_file=str(args.ibm_api_key_file) if ibm else None,
                ibm_max_execution_time=60 if ibm else None, aer_noise=args.aer_noise,
                qaoa_output=str(result_path), dry_run=False))
            manifest["status"] = json.loads(result_path.read_text())["status"]
    except (Exception, KeyboardInterrupt) as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error).replace(token, "[REDACTED]") if token else str(error)
        with log_path.open("a") as log:
            log.write(traceback.format_exc())
        print(f"Smoke test failed: {manifest['error']}", flush=True)
    finally:
        if token and log_path.exists():
            log_path.write_text(log_path.read_text().replace(token, "[REDACTED]"))
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        qaoa_solver.write_result(output / "run.json", manifest)
        archive = output.with_suffix(".zip")
        with ZipFile(archive, "x", ZIP_DEFLATED) as bundle:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(output.parent))
        print(f"Status: {manifest['status']}\nZIP: {archive}", flush=True)
    return 0 if manifest["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
