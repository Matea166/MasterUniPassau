import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts import make_report as report


class ReportTests(unittest.TestCase):
    def test_current_results_render_without_historical_files(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "results"
            sources = {}
            experiments = [
                ("wetgrass_100", "table_6_03_cardinality_estimates.csv"),
                ("wetgrass_10000", "table_6_05_cardinality_estimates.csv"),
                ("nhanes", "table_6_08_cardinality_estimates.csv"),
                ("market_basket_100", "table_6_10_cardinality_estimates.csv"),
                ("market_basket_10000", "table_6_15_cardinality_estimates.csv"),
                ("random_control", "table_6_14_random_structure_check.csv"),
                ("tpcds_store_sales", "cardinality_estimates.csv"),
                ("tpcds_store_sales", "qerror_summary.csv"),
                ("tpcds_store_sales", "solver_settings.csv"),
            ]
            for experiment, filename in experiments:
                path = results / experiment / "reproduced_tables" / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame({"query_id": [experiment], "estimate": [12.3456789],
                              "sql": ["SELECT * FROM t;"], "reason": ["test"]}).to_csv(path, index=False)
                sources[path] = path.read_bytes()
            images = ["market_basket_100/figure_6_1_sorted_qerror.png",
                      "market_basket_100/combined_results.png",
                      "tpcds_store_sales/combined_results.png"]
            for image in images:
                (results / image).write_bytes(b"png")
            with patch.object(report, "RESULTS_ROOT", str(results)), \
                    patch.object(report, "REPO_ROOT", str(Path(__file__).resolve().parents[1])):
                report.main()
            rendered = (results / "index.html").read_text()
            self.assertEqual(rendered.count("<table "), len(experiments) + 4)
            self.assertEqual(rendered.count("<details>"), 4)
            self.assertIn('id="queries"', rendered)
            for workload in (Path(report.__file__).resolve().parents[1] / "workloads").glob("*.csv"):
                for query in pd.read_csv(workload).itertuples():
                    condition = query.sql.split(" WHERE ", 1)[1].rstrip(";")
                    self.assertIn(report.html.escape(condition, quote=False), rendered)
            self.assertIn("<th>Condition</th>", rendered)
            self.assertNotIn("SELECT * FROM", rendered)
            for path, content in sources.items():
                self.assertIn(f'href="{path.relative_to(results)}"', rendered)
                self.assertEqual(path.read_bytes(), content)
            for image in images:
                self.assertIn(f'src="{image}"', rendered)
            for experiment, _ in experiments:
                self.assertIn(f"<td>{experiment}</td>", rendered)
            self.assertIn("12.346", rendered)
            self.assertNotIn("SELECT * FROM t;", rendered)
            self.assertNotIn("Original (thesis)", rendered)
            self.assertNotIn('class="missing"', rendered)

    def test_unrun_experiments_show_missing_results(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "results"
            (results / "nhanes/reproduced_tables").mkdir(parents=True)
            with patch.object(report, "RESULTS_ROOT", str(results)):
                report.main()
            rendered = (results / "index.html").read_text()
            self.assertEqual(rendered.count("Results not generated yet."), 6)
            self.assertIn("TPC-DS results not generated yet.", rendered)
            self.assertNotIn("Download CSV", rendered)


if __name__ == "__main__":
    unittest.main()
