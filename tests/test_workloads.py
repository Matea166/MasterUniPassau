import itertools
import sqlite3
import unittest
from pathlib import Path

import pandas as pd

from bnsl.workloads import TABLES, load_queries, query_filters


class WorkloadTests(unittest.TestCase):
    def representations(self):
        wetgrass = pd.DataFrame(itertools.product(["f", "t"], ["off", "on"], ["f", "t"], ["f", "t"]),
                                columns=["Cloud", "Sprinkler", "Rain", "WetGrass"])
        market = pd.DataFrame(itertools.product([0, 1], repeat=6),
                              columns=["Beer", "Bread", "Cola", "Diapers", "Eggs", "Milk"])
        path = Path(__file__).resolve().parents[1] / "bnsl/datasets/data/NHANES_age_prediction.csv"
        nhanes = pd.read_csv(path)[["age_group", "BMXBMI", "RIAGENDR", "DIQ010"]]
        binned = pd.cut(nhanes.BMXBMI, [0, 18.5, 25, 30, 150], labels=[0, 1, 2, 3], right=False)
        tree = nhanes.astype(str)
        tree["BMXBMI"] = binned.astype(str)
        annealing = pd.DataFrame({"age_group": nhanes.age_group.map({"Adult": 0, "Senior": 1}),
                                 "BMXBMI": binned.astype(int),
                                 "RIAGENDR": nhanes.RIAGENDR.map({1: 0, 2: 1}),
                                 "DIQ010": nhanes.DIQ010.map({1: 0, 2: 1, 3: 2})})
        return [("wetgrass", wetgrass, wetgrass.astype(str)),
                ("wetgrass", wetgrass, wetgrass.rename(columns=str.lower).astype("category")),
                ("market_basket", market, market.astype(str)),
                ("market_basket", market, market.astype("category")),
                ("nhanes", nhanes, tree), ("nhanes", nhanes, annealing)]

    def test_all_workload_predicates_match_sql(self):
        for dataset, raw, modeled in self.representations():
            with self.subTest(dataset=dataset, types=str(modeled.dtypes.tolist())):
                queries = load_queries(dataset, raw, modeled)
                self.assertEqual(len(queries), 20)
                with sqlite3.connect(":memory:") as connection:
                    raw.to_sql(TABLES[dataset], connection, index=False)
                    for sql, filters in queries:
                        expected = {row[0] for row in connection.execute(sql.replace("SELECT *", "SELECT rowid - 1"))}
                        mask = pd.Series(True, index=modeled.index)
                        for column, value in filters.items():
                            mask &= modeled[column].eq(value)
                        self.assertEqual(set(modeled.index[mask]), expected, sql)

    def test_partial_bmi_group_is_rejected(self):
        dataset, raw, modeled = self.representations()[-1]
        sql = "SELECT * FROM nhanes_data WHERE BMXBMI >= 20 AND BMXBMI < 25;"
        with self.assertRaisesRegex(ValueError, "complete BMI group"):
            query_filters(sql, dataset, raw, modeled)

    def test_unknown_predicate_is_rejected(self):
        dataset, raw, modeled = self.representations()[0]
        for sql in ["SELECT * FROM wetgrass_data WHERE unknown = 't';",
                    "SELECT * FROM wetgrass_data WHERE cloud = 't' OR rain = 't';"]:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                query_filters(sql, dataset, raw, modeled)

    def test_zero_result_combination_is_kept(self):
        raw = pd.DataFrame({"Beer": [0, 1], "Bread": [1, 0], "Cola": [0, 1],
                            "Diapers": [1, 0], "Eggs": [0, 1], "Milk": [1, 0]})
        queries = load_queries("market_basket", raw, raw)
        sql, filters = queries[-1]
        self.assertEqual(filters, {"Eggs": 1, "Milk": 1})
        mask = pd.Series(True, index=raw.index)
        for column, value in filters.items():
            mask &= raw[column].eq(value)
        self.assertEqual(int(mask.sum()), 0)

    def test_misaligned_encoding_is_rejected(self):
        dataset, raw, modeled = self.representations()[0]
        with self.assertRaisesRegex(ValueError, "same row index"):
            load_queries(dataset, raw, modeled.iloc[::-1])
        modeled.loc[1, "WetGrass"] = "f"
        with self.assertRaisesRegex(ValueError, "predicates differ"):
            load_queries(dataset, raw, modeled)


if __name__ == "__main__":
    unittest.main()
