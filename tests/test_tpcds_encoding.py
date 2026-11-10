import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from pgmpy.inference import VariableElimination

from bnsl.cardinality_estimation import cardinality_estimation_tpcds as tree
from bnsl.datasets.tpcds_encoding import (
    COLUMNS, DATA_PATH, ROOT, STATE_NAMES, encode, load_queries,
    matching_rows, query_filters, tree_data, write_solver_input,
)
from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation


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

    def test_invalid_values_are_rejected(self):
        for column, value in [("ss_quantity", 1.5), ("ss_quantity", 101), ("ss_sales_price", 0.001),
                              ("ss_wholesale_cost", -1), ("ss_store_sk", 3), ("ss_net_profit", np.inf)]:
            with self.subTest(column=column, value=value):
                raw = self.raw.iloc[:1].copy()
                raw[column] = value
                with self.assertRaises(ValueError):
                    encode(raw)

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
        self.assertAlmostEqual(tree.estimate_probability(model, {"ss_net_profit": [0]}), 0.5)
        self.assertAlmostEqual(tree.estimate_probability(model, {"ss_net_profit": [1, 2]}), 0.5)

    def test_tree_matches_independent_mle_inference(self):
        model = tree.fit_model(self.encoded)
        matrix = np.zeros((8, 8), dtype=int)
        for parent, child in model.edges():
            matrix[COLUMNS.index(parent), COLUMNS.index(child)] = 1
        mle = annealing.fit_model(self.encoded, matrix)
        inference = VariableElimination(mle)
        filters = [item[1] for item in self.queries]
        filters += [{column: [STATE_NAMES[column][-1]]} for column in COLUMNS]
        filters += [{"ss_quantity": [1, 2, 3]}]
        for query in filters + list(reversed(filters)):
            expected = annealing.estimate_probability(inference, query)
            self.assertAlmostEqual(tree.estimate_probability(model, query), expected, places=12)
        matrix[3, :] = 0
        matrix[:, 3] = 0
        matrix[0, 3] = matrix[1, 3] = 1
        two_parent = annealing.fit_model(self.encoded, matrix)
        two_parent_inference = VariableElimination(two_parent)
        for _, query in self.queries:
            probability = annealing.estimate_probability(two_parent_inference, query)
            self.assertTrue(np.isfinite(probability) and 0 <= probability <= 1)

    def test_tree_cli_exports_standard_csv_and_graph(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "result.csv"
            with patch.object(tree, "ROOT", root), patch("sys.argv", [
                "estimate", "--input", str(DATA_PATH), "--output", str(output),
            ]):
                tree.main()
            result = pd.read_csv(output)
            self.assertEqual(result.columns.tolist(), [
                "query_sql", "true_cardinality", "bn_est_cardinality", "est_selectivity",
            ])
            self.assertEqual(len(result), len(self.queries))
            graph = root / "output_bn" / (DATA_PATH.stem + "_bn.png")
            self.assertTrue(graph.is_file())
            self.assertGreater(graph.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
