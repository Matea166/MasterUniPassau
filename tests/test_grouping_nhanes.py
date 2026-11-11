import importlib.util
import unittest
from pathlib import Path

import pandas as pd

from bnsl.datasets.grouping_nhanes import category_mappings, encode, tree_data


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "bnsl/datasets/data/NHANES_age_prediction.csv"


class NhanesGroupingTests(unittest.TestCase):
    def test_existing_solver_and_tree_representations_are_preserved(self):
        raw = pd.read_csv(DATA_PATH)
        binned = pd.cut(raw.BMXBMI, [0, 18.5, 25, 30, 150],
                        labels=[0, 1, 2, 3], right=False)
        expected = pd.DataFrame({
            "age_group": raw.age_group.map({"Adult": 0, "Senior": 1}).astype("int8"),
            "BMXBMI": binned.astype(int),
            "RIAGENDR": raw.RIAGENDR.map({1: 0, 2: 1}).astype("int8"),
            "DIQ010": raw.DIQ010.map({1: 0, 2: 1, 3: 2}).astype("int8"),
        })
        pd.testing.assert_frame_equal(encode(raw), expected)
        expected_tree = raw[["age_group", "RIAGENDR", "DIQ010", "BMXBMI"]].astype(str)
        expected_tree["BMXBMI"] = binned.astype(str)
        pd.testing.assert_frame_equal(tree_data(raw), expected_tree)
        self.assertEqual(category_mappings(raw), {
            "age_group": {0: "Adult", 1: "Senior"},
            "RIAGENDR": {0: 1, 1: 2},
            "DIQ010": {0: 1, 1: 2, 2: 3},
        })
        spec = importlib.util.spec_from_file_location(
            "nhanes_annealing", ROOT / "bnsl-qa/cardinality_estimation/cardinality_estimation_NHANES.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded_raw, loaded_encoded = module.load_data(DATA_PATH)
        pd.testing.assert_frame_equal(loaded_raw, raw)
        pd.testing.assert_frame_equal(loaded_encoded, expected)

    def test_bmi_boundaries_and_row_order(self):
        raw = pd.DataFrame({
            "age_group": ["Senior", "Adult"] * 4,
            "BMXBMI": [0, 18.49, 18.5, 24.99, 25, 29.99, 30, 149.99],
            "RIAGENDR": [2, 1] * 4,
            "DIQ010": [3, 1] * 4,
        }, index=[9, 3, 14, 2, 8, 5, 1, 6])
        encoded = encode(raw)
        modeled = tree_data(raw)
        self.assertTrue(encoded.index.equals(raw.index))
        self.assertTrue(modeled.index.equals(raw.index))
        self.assertEqual(encoded.BMXBMI.tolist(), [0, 0, 1, 1, 2, 2, 3, 3])
        self.assertEqual(modeled.BMXBMI.tolist(), ["0", "0", "1", "1", "2", "2", "3", "3"])
        self.assertEqual(encoded.age_group.tolist(), [1, 0] * 4)
        self.assertEqual(modeled.age_group.tolist(), raw.age_group.tolist())
        self.assertEqual(encoded.DIQ010.tolist(), [1, 0] * 4)
        self.assertEqual(modeled.DIQ010.tolist(), ["3", "1"] * 4)

    def test_invalid_bmi_keeps_existing_behavior(self):
        for value in [float("nan"), -1, 150]:
            with self.subTest(value=value):
                raw = pd.DataFrame({"age_group": ["Adult"], "BMXBMI": [value],
                                    "RIAGENDR": [1], "DIQ010": [1]})
                with self.assertRaises(ValueError):
                    encode(raw)
                expected = pd.cut(raw.BMXBMI, [0, 18.5, 25, 30, 150],
                                  labels=[0, 1, 2, 3], right=False).astype(str)
                pd.testing.assert_series_equal(tree_data(raw).BMXBMI, expected)


if __name__ == "__main__":
    unittest.main()
