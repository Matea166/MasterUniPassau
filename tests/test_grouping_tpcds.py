import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from pgmpy.inference import VariableElimination

from bnsl.cardinality_estimation import cardinality_estimation_tpcds as tree
from bnsl.datasets.grouping_tpcds import (
    COLUMNS, DATA_PATH, ROOT, STATE_NAMES, encode, load_queries,
    matching_rows, query_filters, tree_data, write_solver_input,
)
from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation
from bnsl.workloads import load_queries as load_workload_queries


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


annealing = load_module("tpcds_annealing", ROOT / "bnsl-qa/cardinality_estimation/cardinality_estimation_TPCDS.py")
qubo = load_module("tpcds_qubo", ROOT / "bnsl-qa/bnslqa/solvers/qubo_values.py")


class TpcdsEncodingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = pd.read_csv(DATA_PATH)
        cls.encoded = encode(cls.raw)
        cls.queries = load_queries()

    def run_tree(self, raw, sql_queries=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_dir = root / "bnsl/datasets/data"
            data_dir.mkdir(parents=True)
            raw.to_csv(data_dir / "TPCDS_test.csv", index=False)
            if sql_queries is None:
                sql_queries = [row["sql"] for row, _ in self.queries]
            workload = root / "queries.csv"
            pd.DataFrame({
                "query_id": [f"Q{i}" for i in range(len(sql_queries))],
                "sql": sql_queries,
            }).to_csv(workload, index=False)

            def load_test_queries(dataset, raw, modeled):
                return load_workload_queries(dataset, raw, modeled, path=workload)

            previous_dir = Path.cwd()
            try:
                os.chdir(root / "bnsl")
                with patch.dict(os.environ, {"CSV_FILE": "TPCDS_test"}), patch.object(
                    tree, "load_queries", side_effect=load_test_queries
                ):
                    tree.main()
            finally:
                os.chdir(previous_dir)
            outputs = list((root / "bnsl/card_results").glob("result_TPCDS_test_*.csv"))
            self.assertEqual(len(outputs), 1)
            graph = root / "output_bn/TPCDS_test_bn.png"
            return pd.read_csv(outputs[0]), graph.read_bytes()

    def test_rows_and_missing_states(self):
        self.assertEqual(self.encoded.shape, (10000, 8))
        self.assertEqual(list(self.encoded.columns), COLUMNS)
        self.assertTrue(self.raw.index.equals(self.encoded.index))
        self.assertEqual(int(self.raw.isna().any(axis=1).sum()), 856)
        categories = tree_data(self.encoded)
        for column in COLUMNS:
            self.assertEqual(set(self.encoded[column]), set(STATE_NAMES[column]))
            missing = self.encoded[column].eq(STATE_NAMES[column][-1])
            pd.testing.assert_series_equal(missing, self.raw[column].isna())
            pd.testing.assert_series_equal(categories[column].eq("MISSING"), missing)
        pd.testing.assert_series_equal(self.encoded.ss_net_profit.eq(0),
                                       self.raw.ss_net_profit.lt(0))

    def test_annealing_loader_matches_solver_encoding(self):
        raw, encoded = annealing.load_data(DATA_PATH)
        pd.testing.assert_frame_equal(raw, self.raw)
        pd.testing.assert_frame_equal(encoded, self.encoded)

    def test_common_workload_loader_matches_tpcds_parser(self):
        expected = [(row["sql"], filters) for row, filters in self.queries]
        self.assertEqual(load_workload_queries("tpcds_store_sales", self.raw, self.encoded), expected)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queries.csv"
            queries = [
                "SELECT * FROM store_sales WHERE ss_coupon_amt IS NULL;",
                "SELECT * FROM store_sales WHERE ss_coupon_amt IS NOT NULL;",
                "SELECT * FROM store_sales WHERE ss_quantity > 25;",
                "SELECT * FROM store_sales WHERE ss_coupon_amt IS NULL AND ss_coupon_amt = 0;",
            ]
            pd.DataFrame({"query_id": ["Q1", "Q2", "Q3", "Q4"], "sql": queries}).to_csv(path, index=False)
            actual = load_workload_queries("tpcds_store_sales", self.raw, self.encoded, path=path)
            self.assertEqual(actual, [(sql, query_filters(sql)) for sql in queries])
            for ids in [["Q1", "Q1", "Q3", "Q4"], ["Q1", " ", "Q3", "Q4"]]:
                pd.DataFrame({"query_id": ids, "sql": queries}).to_csv(path, index=False)
                with self.assertRaisesRegex(ValueError, "unique and nonempty"):
                    load_workload_queries("tpcds_store_sales", self.raw, self.encoded, path=path)
        with self.assertRaisesRegex(ValueError, "same row index"):
            load_workload_queries("tpcds_store_sales", self.raw, self.encoded.iloc[::-1])

    def test_annealing_preserves_matrix_order_and_unobserved_states(self):
        encoded = self.encoded.iloc[:1, ::-1]
        matrix = np.zeros((8, 8), dtype=int)
        matrix[0, 3] = matrix[1, 3] = 1
        model = annealing.fit_model(encoded, matrix)
        self.assertEqual(set(model.edges()), {("ss_quantity", "ss_net_profit"),
                                             ("ss_sales_price", "ss_net_profit")})
        for cpd in model.get_cpds():
            for column, states in cpd.state_names.items():
                self.assertEqual(states, STATE_NAMES[column])

    def test_boundaries_and_zero(self):
        cases = {
            "ss_quantity": ([1, 25, 26, 50, 51, 75, 76, 100, None], [0, 0, 1, 1, 2, 2, 3, 3, 4]),
            "ss_sales_price": ([0, 24.99, 25, 49.99, 50, 99.99, 100, None], [0, 0, 1, 1, 2, 2, 3, 4]),
            "ss_coupon_amt": ([0, 0.01, 99.99, 100, 499.99, 500, 999.99, 1000,
                               1999.99, 2000, 12592, None],
                              [0, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 3]),
            "ss_net_profit": ([-9035.60, -2000.01, -2000, -1000.01, -1000, -250.01,
                               -250, -0.01, 0, 249.99, 250, 999.99, 1000, 7824.88, None],
                              [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 3]),
            "ss_wholesale_cost": ([0, 24.99, 25, 49.99, 50, 74.99, 75, None], [0, 0, 1, 1, 2, 2, 3, 4]),
            "ss_net_paid": ([0, 249.99, 250, 999.99, 1000, 1999.99, 2000, 2999.99,
                             3000, 5999.99, 6000, 15891.84, None],
                            [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3]),
            "ss_list_price": ([0, 49.99, 50, 99.99, 100, None], [0, 0, 1, 1, 2, 3]),
            "ss_store_sk": ([1, 2, 4, 7, 8, 10, None], [0, 1, 2, 3, 4, 5, 6]),
        }
        for column, (values, expected) in cases.items():
            with self.subTest(column=column):
                raw = self.raw.iloc[:len(values)].copy()
                raw[column] = values
                self.assertEqual(encode(raw)[column].tolist(), expected)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "boundary.csv"
                    raw.to_csv(path, index=False)
                    _, encoded = annealing.load_data(path)
                    self.assertEqual(encoded[column].tolist(), expected)

    def test_invalid_values_are_rejected(self):
        for column, value in [("ss_quantity", 1.5), ("ss_quantity", 101), ("ss_sales_price", 0.001),
                              ("ss_wholesale_cost", -1), ("ss_store_sk", 3), ("ss_net_profit", np.inf)]:
            with self.subTest(column=column, value=value):
                raw = self.raw.iloc[:1].copy()
                raw[column] = value
                with self.assertRaises(ValueError):
                    encode(raw)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "invalid.csv"
                    raw.to_csv(path, index=False)
                    with self.assertRaises(ValueError):
                        annealing.load_data(path)

    def test_sql_and_encoding_select_identical_rows(self):
        reference = json.loads((ROOT / "reference_results/tpcds_store_sales_postgres.json").read_text())
        counts = {row["query_id"]: row["true_cardinality"] for row in reference["results"]}
        with sqlite3.connect(":memory:") as connection:
            self.raw.to_sql("store_sales", connection, index=False)
            for query, filters in self.queries:
                with self.subTest(query=query["query_id"]):
                    sql = query["sql"].replace("SELECT *", "SELECT rowid - 1")
                    expected = {row[0] for row in connection.execute(sql)}
                    actual = set(self.encoded.index[matching_rows(self.encoded, filters)])
                    self.assertEqual(actual, expected)
                    self.assertEqual(len(actual), counts[query["query_id"]])

    def test_query_boundaries_and_nulls(self):
        def filters(condition):
            return query_filters("SELECT * FROM store_sales WHERE " + condition + ";")
        self.assertEqual(filters("ss_quantity > 25"), {"ss_quantity": [1, 2, 3]})
        self.assertEqual(filters("ss_coupon_amt > 0"), {"ss_coupon_amt": [1, 2]})
        self.assertEqual(filters("ss_coupon_amt >= 1000"), {"ss_coupon_amt": [2]})
        self.assertEqual(filters("ss_net_profit < 0"), {"ss_net_profit": [0]})
        self.assertEqual(filters("ss_net_paid < 1000"), {"ss_net_paid": [0]})
        self.assertEqual(filters("ss_net_paid >= 3000"), {"ss_net_paid": [2]})
        self.assertEqual(filters("ss_coupon_amt IS NULL"), {"ss_coupon_amt": [3]})
        self.assertEqual(filters("ss_coupon_amt IS NOT NULL"), {"ss_coupon_amt": [0, 1, 2]})
        self.assertEqual(filters("ss_coupon_amt IS NULL AND ss_coupon_amt = 0"), {"ss_coupon_amt": []})
        self.assertEqual(filters("ss_coupon_amt >= 1000 AND ss_coupon_amt < 1000"), {"ss_coupon_amt": []})
        with self.assertRaisesRegex(ValueError, "cuts through"):
            filters("ss_sales_price >= 73.40")
        with self.assertRaises(ValueError):
            filters("ss_quantity = 1 OR ss_quantity = 2")

    def test_solver_input_counts_missing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tpcds.txt"
            write_solver_input(self.encoded, path)
            examples, n, states = qubo.getExamples(path)
        self.assertEqual(n, 8)
        self.assertEqual(states, [5, 5, 4, 4, 5, 4, 4, 7])
        self.assertEqual(examples, self.encoded.to_numpy().tolist())
        for child, parents in [(i, ()) for i in range(8)] + [(0, (1, 7)), (3, (0, 6)), (7, (3, 4))]:
            count = sum(qubo.calcNijSum(examples, parents, child, j, states)
                        for j in range(qubo.calcQi(parents, states)))
            self.assertEqual(count, len(examples))

    def test_missing_parent_is_marginalized(self):
        raw = self.raw.iloc[:4].copy()
        raw["ss_store_sk"] = [1, None, 1, 2]
        raw["ss_net_profit"] = [-1, 1, -1, 1]
        encoded = encode(raw)
        model = BayesianNetwork([("ss_store_sk", "ss_net_profit")])
        model.update(Relation(tree_data(encoded[["ss_store_sk", "ss_net_profit"]])))
        self.assertAlmostEqual(model.p(ss_net_profit="0"), 0.5)
        self.assertAlmostEqual(sum(model.p(ss_net_profit=str(code)) for code in [1, 2]), 0.5)

    def test_tree_matches_independent_mle_inference(self):
        model = BayesianNetwork(cl_max_rows=30000).fit(Relation(tree_data(self.encoded)))
        matrix = np.zeros((8, 8), dtype=int)
        for parent, child in model.edges():
            matrix[COLUMNS.index(parent), COLUMNS.index(child)] = 1
        mle = annealing.fit_model(self.encoded, matrix)
        inference = VariableElimination(mle)
        queries = [row["sql"] for row, _ in self.queries]
        queries += [f"SELECT * FROM store_sales WHERE {column} IS NULL;" for column in COLUMNS]
        queries += ["SELECT * FROM store_sales WHERE ss_quantity > 25;",
                    "SELECT * FROM store_sales WHERE ss_coupon_amt IS NOT NULL;",
                    "SELECT * FROM store_sales WHERE ss_coupon_amt IS NULL AND ss_coupon_amt = 0;"]
        queries += list(reversed(queries))
        result, _ = self.run_tree(self.raw, queries)
        self.assertEqual(result.query_sql.tolist(), queries)
        for sql, (_, row) in zip(queries, result.iterrows()):
            query = query_filters(sql)
            expected = annealing.estimate_probability(inference, query)
            self.assertAlmostEqual(row.est_selectivity, expected, places=12)
            self.assertAlmostEqual(row.bn_est_cardinality, expected * len(self.raw), places=9)
            self.assertEqual(row.true_cardinality, int(matching_rows(self.encoded, query).sum()))
        matrix[3, :] = 0
        matrix[:, 3] = 0
        matrix[0, 3] = matrix[1, 3] = 1
        two_parent = annealing.fit_model(self.encoded, matrix)
        two_parent_inference = VariableElimination(two_parent)
        for _, query in self.queries:
            probability = annealing.estimate_probability(two_parent_inference, query)
            self.assertTrue(np.isfinite(probability) and 0 <= probability <= 1)

    def test_tree_exports_standard_csv_and_graph(self):
        result, graph = self.run_tree(self.raw)
        self.assertEqual(result.columns.tolist(), [
            "query_sql", "true_cardinality", "bn_est_cardinality", "est_selectivity",
        ])
        self.assertEqual(len(result), len(self.queries))
        self.assertTrue(graph.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
