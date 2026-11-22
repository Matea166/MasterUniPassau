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
    generateExpected(data, variables, problem["toporder"], states, 11, counts)
    columns = ["Rain", "WetGrass"]
    positions = [list(variables).index(name) for name in columns]
    source_rows = data.getvalue().splitlines()
    rows = [[int(row.split()[i]) for i in positions] for row in source_rows]
    path = output / "WetGrass_smoke.txt"
    n = len(columns)
    header = " ".join(map(str, [n] + [states[name] for name in columns]))
    solution = " ".join(["0"] * (n * (n - 1)))
    path.write_text(f"{header}\nWetGrass_smoke_{'_'.join(columns)}\n{solution}\n" +
                    "".join(" ".join(map(str, row)) + "\n" for row in rows))
    return path, {"source": "bnsl-qa/problems/WetGrass.json", "columns": columns,
                  "rows": len(rows), "requested_rows": 11, "source_rows": len(source_rows),
                  "states": {name: variables[name]["states"] for name in columns}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qaoa-backend", choices=["aer", "ibm"], default="ibm")
    parser.add_argument("--ibm-backend", default=os.environ.get("IBM_BACKEND"))
    parser.add_argument("--ibm-instance", default=os.environ.get("IBM_INSTANCE"))
    secret = Path("/run/secrets/ibm_api_key")
    parser.add_argument("--ibm-api-key-file", type=Path, default=secret if secret.is_file() else None)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/ibm")
    args = parser.parse_args()
    ibm = args.qaoa_backend == "ibm"
    output = args.output_dir.resolve() / f"smoke_{time_ns()}"
    output.mkdir(parents=True)
    result_path = output / "result.json"
    log_path = output / "run.log"
    manifest = {"status": "running", "scenario": "WetGrass Rain/WetGrass projection",
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "qaoa_backend": args.qaoa_backend, "ibm_backend": (args.ibm_backend or "auto") if ibm else None,
                "reps": 1, "optimizer": "COBYLA",
                "shots_per_evaluation": 1024, "final_shots": 1024, "seed": 42,
                "aer_noise": "none", "max_ibm_jobs": 1 if ibm else 0,
                "python": platform.python_version()}
    token = ""
    print(f"Running {args.qaoa_backend} smoke test. Results: {output}", flush=True)
    try:
        with log_path.open("w") as log, redirect_stdout(log), redirect_stderr(log):
            manifest["versions"] = {name: version(name) for name in
                                    ("qiskit", "qiskit-aer", "qiskit-ibm-runtime", "numpy", "scipy")}
            if ibm:
                if args.ibm_api_key_file:
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
                dataset=str(dataset), reps=1, shots=1024, final_shots=1024,
                seed=42, qaoa_backend=args.qaoa_backend,
                ibm_backend=args.ibm_backend if ibm else None,
                ibm_instance=args.ibm_instance if ibm else None,
                ibm_api_key_file=str(args.ibm_api_key_file) if ibm and args.ibm_api_key_file else None,
                qaoa_output=str(result_path), dry_run=False))
            result = json.loads(result_path.read_text())
            manifest.update(status=result["status"], qubits=result["qubits"])
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
