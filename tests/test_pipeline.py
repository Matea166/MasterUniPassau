import csv
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def test_configuration_budgets_are_preserved(self):
        expected = {
            "wetgrass_100": (["30:10", "30:50", "30:100", "30:250", "30:500",
                               "5:100", "10:100", "20:100", "50:100"], "30:100"),
            "wetgrass_10000": (["20:100", "20:500", "20:1000", "20:5000", "20:10000",
                                 "1:1000", "5:1000", "10:1000", "50:1000"], "20:1000"),
            "market_basket_100": (["30:10", "30:50", "30:100", "30:250", "30:500",
                                    "5:100", "10:100", "20:100", "50:100"], "30:250"),
            "market_basket_10000": (["20:100", "20:500", "20:1000", "20:5000", "20:10000",
                                      "1:1000", "5:1000", "10:1000", "50:1000"], "20:1000"),
            "nhanes": (["10:100", "10:500", "10:1000", "10:2500", "5:1000", "20:1000"], "10:100"),
        }
        for dataset in [*expected, "tpcds_store_sales"]:
            for quick in ("0", "1"):
                for solver in ("SA", "SQA"):
                    with self.subTest(dataset=dataset, quick=quick, solver=solver):
                        command = ('source "$REPO_ROOT/scripts/lib.sh"; '
                                   'source "$REPO_ROOT/config/$DATASET.env"; '
                                   'build_config_pairs "$SOLVER"; printf "%s\\n" "${CONFIG_PAIRS[@]}"')
                        env = dict(os.environ, REPO_ROOT=str(ROOT), DATASET=dataset, QUICK=quick, SOLVER=solver)
                        run = subprocess.run(["bash", "-c", command], env=env, capture_output=True, text=True)
                        self.assertEqual(run.returncode, 0, run.stderr)
                        if dataset == "tpcds_store_sales":
                            wanted = ["20:100" if solver == "SA" else "10:1000"]
                        else:
                            full, headline = expected[dataset]
                            wanted = full if quick == "0" else [headline]
                        self.assertEqual(run.stdout.splitlines(), wanted)

    def dispatch_fixture(self, root, fail_trial=False, mismatch=False):
        (root / "qa-datasets").mkdir()
        (root / "qa-datasets/demo.txt").write_text("fixture\n")
        shutil.copy(ROOT / "bnsl-qa/dispatch.sh", root / "dispatch.sh")
        (root / "estimate.py").write_text(
            "import sys,pathlib\n"
            "out=pathlib.Path(sys.argv[2]); out.mkdir(exist_ok=True,parents=True)\n"
            "rows='query_sql,estimated_cardinality\\nSELECT * FROM t WHERE x=1;,1\\n'\n"
            "if not (" + repr(mismatch) + " and sys.argv[3]=='2'): rows+='SELECT * FROM t WHERE x=2;,2\\n'\n"
            "(out / ('graph_'+sys.argv[3]+'_cardinality.csv')).write_text(rows)\n")
        (root / "bin").mkdir()
        wrapper = root / "bin/python3"
        wrapper.write_text(
            "#!" + sys.executable + "\nimport sys,os,pathlib\n"
            "if sys.argv[1:3]==['-m','bnslqa']:\n"
            " p=pathlib.Path('calls'); n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1))\n"
            " if n and " + repr(fail_trial) + ": sys.exit(9)\n"
            " print('Solution adjacency matrix:\\n'+ ('[0, 1, 0]\\n[0, 0, 1]\\n[0, 0, 0]\\n' if n==0 else '[0, 0, 1]\\n[0, 0, 0]\\n[0, 0, 0]\\n')); sys.exit(0)\n"
            "os.execv(" + repr(sys.executable) + ", [" + repr(sys.executable) + "]+sys.argv[1:])\n")
        wrapper.chmod(0o755)
        env = dict(os.environ, PATH=str(root / "bin") + ":" + os.environ["PATH"],
                   DATASET_TXT="qa-datasets/demo.txt", SOLVER="SA", TRIALS="2", READS="1", CE_SCRIPT="estimate.py")
        return subprocess.run(["bash", "dispatch.sh"], cwd=root, env=env, capture_output=True, text=True)

    def test_failed_trial_stops_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            run = self.dispatch_fixture(Path(folder), fail_trial=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("failed on trial 2", run.stderr)
            self.assertNotIn("DISPATCH_FINAL_CSV=", run.stdout)

    def test_mismatched_graph_queries_stop_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            run = self.dispatch_fixture(Path(folder), mismatch=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("Query mismatch", run.stderr)
            self.assertNotIn("DISPATCH_FINAL_CSV=", run.stdout)

    def test_random_results_align_queries_and_graph_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copy(ROOT / "bnsl-qa/RNG_matrix.sh", root)
            (root / "matrices.txt").write_text("[[0]]\n" * 10)
            (root / "estimate.py").write_text(
                "import sys,pathlib,csv\n"
                "index=int(sys.argv[3]); rows=[['SELECT * FROM t WHERE x=1;',index],['SELECT * FROM t WHERE x=2;',index*2]]\n"
                "with (pathlib.Path(sys.argv[2])/('graph_'+str(index)+'_cardinality.csv')).open('w') as handle:\n"
                " writer=csv.writer(handle); writer.writerow(['query_sql','estimated_cardinality']); writer.writerows(rows[::-1] if index%2==0 else rows)\n")
            env = dict(os.environ, RNG_ACTION="estimate", CARD_SCRIPT="estimate.py", MATRIX_FILE="matrices.txt")
            run = subprocess.run(["bash", "RNG_matrix.sh"], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            final = next(root.glob("RNG_Matrix/results/*/final_queries_cardinality.csv"))
            with final.open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["matrix_2"], "2")
            self.assertEqual(rows[0]["matrix_10"], "10")
            self.assertEqual(rows[1]["matrix_10"], "20")

    def test_shared_runner_handles_tree_paths_and_separate_solver_budgets(self):
        for dataset in ("market_basket_10000", "tpcds_store_sales"):
            with self.subTest(dataset=dataset), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                for directory in ("scripts", "config", "bnsl/datasets/data", "bnsl-qa/qa-datasets"):
                    (root / directory).mkdir(parents=True)
                shutil.copy(ROOT / "scripts/lib.sh", root / "scripts/lib.sh")
                shutil.copy(ROOT / f"config/{dataset}.env", root / f"config/{dataset}.env")
                if dataset == "tpcds_store_sales":
                    csv_name, solver_name = "TPCDS_store_sales_10000", "TPCDS_store_sales_10000"
                else:
                    csv_name, solver_name = "DataMining_MarketBasket_10000", "MarketBasket10000"
                (root / f"bnsl/datasets/data/{csv_name}.csv").write_text("fixture\n")
                (root / f"bnsl-qa/qa-datasets/{solver_name}.txt").write_text("fixture\n")
                (root / "bnsl-qa/dispatch.sh").write_text(
                    'mkdir -p dispatch_output/results\n'
                    'file="dispatch_output/results/$SOLVER.csv"\n'
                    'printf "query_sql,Graph_1.png\\nSELECT * FROM t WHERE x=1;,1\\n" > "$file"\n'
                    'echo "DISPATCH_SOLVER_DIR=dispatch_output/solver_outputs/$SOLVER/run"\n'
                    'echo "DISPATCH_FINAL_CSV=$file"\n')
                (root / "bnsl-qa/qerror_calculation.sh").write_text(
                    'mkdir -p q-error_output\n'
                    'printf "q_error\\n1\\n" > q-error_output/result.csv\n'
                    'echo QERROR_RESULT_FILE=q-error_output/result.csv\n')
                (root / "bnsl/cardinality_benchmarks.sh").write_text(
                    'mkdir -p card_results\n'
                    'printf "query_sql,true_cardinality,bn_est_cardinality,pg_est_cardinality\\nSELECT * FROM t WHERE x=1;,1,1,1\\n" > card_results/final.csv\n'
                    'if [ "$CSV_FILE" = TPCDS_store_sales_10000 ]; then\n'
                    ' echo "BENCH_FINAL_CSV=$PWD/card_results/final.csv"\n'
                    'else echo BENCH_FINAL_CSV=card_results/final.csv; fi\n')
                (root / "bnsl/merge_results.sh").write_text(
                    'test -f "$SA_FILE" && test -f "$SQA_FILE" && test -f "$BN_FILE" || exit 8\n'
                    'printf "fixture\\n" > "$MERGE_OUTPUT_DIR/combined_results_fixture.csv"\n'
                    'touch "$MERGE_OUTPUT_DIR/combined_results_fixture.png"\n')
                driver = ('source "$REPO_ROOT/scripts/lib.sh"\n'
                          'ensure_database() { :; }\n'
                          'import_csv_into_db() { echo import >> "$REPO_ROOT/preparation"; }\n'
                          'prepare_tpcds() { echo tpcds >> "$REPO_ROOT/preparation"; }\n'
                          'run_ce_experiment "config/$DATASET.env"\n')
                env = dict(os.environ, REPO_ROOT=str(root), DATASET=dataset, QUICK="1")
                run = subprocess.run(["bash", "-c", driver], env=env, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                output = root / "results" / dataset
                self.assertFalse((output / ".running").exists())
                with (output / "configurations.csv").open() as handle:
                    budgets = [(r["solver"], int(r["trials"]), int(r["reads"])) for r in csv.DictReader(handle)]
                expected = [("SA", 20, 100), ("SQA", 10, 1000)] if dataset == "tpcds_store_sales" else [("SA", 20, 1000), ("SQA", 20, 1000)]
                self.assertEqual(budgets, expected)
                self.assertTrue((output / "combined_results.csv").is_file())
                self.assertEqual((root / "preparation").read_text().strip(),
                                 "tpcds" if dataset == "tpcds_store_sales" else "import")


if __name__ == "__main__":
    unittest.main()
