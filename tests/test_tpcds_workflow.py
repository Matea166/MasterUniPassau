import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from scripts import summarize_results as summary


class TpcdsReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.exp = self.root / "results/tpcds_store_sales"
        (self.exp / "estimates").mkdir(parents=True)
        (self.root / "config").mkdir()
        (self.root / "workloads").mkdir()
        source = Path(__file__).resolve().parents[1]
        shutil.copy(source / "config/tpcds_store_sales.env", self.root / "config")
        self.workload = pd.DataFrame({
            "query_id": ["Q02", "Q01"],
            "sql": ["SELECT * FROM store_sales WHERE ss_quantity = 2;",
                    "SELECT * FROM store_sales WHERE ss_quantity = 1;"],
            "reason": ["Rare", "Common"],
        })
        self.workload.to_csv(self.root / "workloads/tpcds_store_sales.csv", index=False)
        self.truth = pd.DataFrame({
            "query_sql": self.workload["sql"][::-1].tolist(),
            "true_cardinality": [1, 10],
            "bn_est_cardinality": [1, 8],
            "pg_est_cardinality": [1, 7],
        })
        self.truth.to_csv(self.exp / "chowliu_pg_final.csv", index=False)
        self.estimates = pd.DataFrame({
            "query_sql": self.truth["query_sql"],
            "Graph_1": [1.004, 8.001],
            "Graph_2": [1.003, 8.002],
        })
        for solver, trials, reads in [("SA", 20, 100), ("SQA", 10, 1000)]:
            self.estimates.to_csv(self.exp / f"estimates/estimates_{solver}_T{trials}_R{reads}.csv", index=False)
        self.patcher = patch.multiple(summary, REPO_ROOT=str(self.root),
                                      RESULTS_ROOT=str(self.root / "results"),
                                      CONFIG_DIR=str(self.root / "config"))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_query_alignment_precision_and_separate_solver_budgets(self):
        summary.summarize_tpcds()
        tables = self.exp / "reproduced_tables"
        results = pd.read_csv(tables / "cardinality_estimates.csv")
        self.assertEqual(results["query_id"].tolist(), ["Q02", "Q01"])
        self.assertEqual(results["true_cardinality"].tolist(), [10, 1])
        self.assertEqual(results["sa_estimate"].tolist(), [8.002, 1.004])
        self.assertAlmostEqual(results["sa_qerror"].iloc[1], 1.004)
        settings = pd.read_csv(tables / "solver_settings.csv")
        self.assertEqual(settings["trials"].tolist(), [20, 10])
        self.assertEqual(settings["reads"].tolist(), [100, 1000])
        self.assertEqual(settings["unique_structures"].tolist(), [2, 2])

    def test_missing_solver_output_stops_summary(self):
        (self.exp / "estimates/estimates_SQA_T10_R1000.csv").unlink()
        with self.assertRaisesRegex(ValueError, "missing SQA estimates"):
            summary.summarize_tpcds()

    def test_query_mismatch_stops_summary(self):
        self.estimates.iloc[:1].to_csv(self.exp / "estimates/estimates_SA_T20_R100.csv", index=False)
        with self.assertRaisesRegex(ValueError, "Query mismatch"):
            summary.summarize_tpcds()

    def test_duplicate_workload_ids_stop_summary(self):
        self.workload["query_id"] = "Q01"
        self.workload.to_csv(self.root / "workloads/tpcds_store_sales.csv", index=False)
        with self.assertRaisesRegex(ValueError, "duplicate query IDs"):
            summary.summarize_tpcds()

    def test_incomplete_run_cannot_generate_summary(self):
        (self.exp / ".running").touch()
        with self.assertRaisesRegex(ValueError, "Incomplete experiment"):
            summary.summarize_tpcds()

    def test_old_configurations_are_excluded(self):
        self.estimates.to_csv(self.exp / "estimates/estimates_SA_T20_R500.csv", index=False)
        (self.exp / "configurations.csv").write_text("solver,trials,reads\nSA,20,100\nSQA,10,1000\n")
        self.assertIsNone(summary.load_estimates(str(self.exp), "SA", 20, 500))
        self.assertIsNotNone(summary.load_estimates(str(self.exp), "SA", 20, 100))

    def test_market_basket_and_tpcds_use_identical_report_columns(self):
        source = Path(__file__).resolve().parents[1]
        market = self.root / "results/market_basket_10000"
        (market / "estimates").mkdir(parents=True)
        self.truth.to_csv(market / "chowliu_pg_final.csv", index=False)
        for solver in ("SA", "SQA"):
            self.estimates.to_csv(market / f"estimates/estimates_{solver}_T20_R1000.csv", index=False)
        self.workload.to_csv(self.root / "workloads/market_basket.csv", index=False)
        summary.summarize_experiment("market_basket_10000",
                                     summary.parse_env(source / "config/market_basket_10000.env"))
        summary.summarize_tpcds()
        for tpcds_name, market_name in [
            ("cardinality_estimates.csv", "table_6_15_cardinality_estimates.csv"),
            ("qerror_summary.csv", "table_6_16_qerror_summary.csv"),
        ]:
            tpcds = pd.read_csv(self.exp / "reproduced_tables" / tpcds_name)
            other = pd.read_csv(market / "reproduced_tables" / market_name)
            pd.testing.assert_frame_equal(tpcds, other)


class WorkflowTests(unittest.TestCase):
    def test_tpcds_runs_before_report_and_failure_stops_workflow(self):
        source = Path(__file__).resolve().parents[1]
        sequence = ["prepare_datasets", "run_wetgrass_100", "run_wetgrass_10000",
                    "run_nhanes", "run_market_basket_100", "run_market_basket_10000",
                    "run_random_control", "run_tpcds_store_sales", "make_report"]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy(source / "scripts/run_all.sh", scripts)
            shutil.copy(source / "scripts/lib.sh", scripts)
            for name in sequence:
                (scripts / f"{name}.sh").write_text(f'echo "{name}" >> "$REPO_ROOT/steps"\n')
            env = dict(os.environ, REPO_ROOT=str(root), QUICK="1")
            run = subprocess.run(["bash", str(scripts / "run_all.sh")], env=env, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual((root / "steps").read_text().splitlines(), sequence)
            (root / "steps").unlink()
            (scripts / "run_tpcds_store_sales.sh").write_text("exit 7\n")
            run = subprocess.run(["bash", str(scripts / "run_all.sh")], env=env, capture_output=True)
            self.assertEqual(run.returncode, 7)
            self.assertEqual((root / "steps").read_text().splitlines(), sequence[:-2])


if __name__ == "__main__":
    unittest.main()
