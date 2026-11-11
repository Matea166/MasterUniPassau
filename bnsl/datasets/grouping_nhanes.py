import pandas as pd

COLUMNS = ["age_group", "BMXBMI", "RIAGENDR", "DIQ010"]
CATEGORICAL_COLUMNS = ["age_group", "RIAGENDR", "DIQ010"]
TREE_COLUMNS = ["age_group", "RIAGENDR", "DIQ010", "BMXBMI"]
BMI_BINS = [0, 18.5, 25.0, 30.0, 150.0]
BMI_STATES = [0, 1, 2, 3]


def encode(raw):
    encoded = raw[COLUMNS].copy()
    encoded["BMXBMI"] = pd.cut(
        raw["BMXBMI"], bins=BMI_BINS, labels=BMI_STATES, right=False
    ).astype(int)
    for column in CATEGORICAL_COLUMNS:
        encoded[column] = raw[column].astype("category").cat.codes
    return encoded


def tree_data(raw):
    modeled = raw[TREE_COLUMNS].copy()
    for column in CATEGORICAL_COLUMNS:
        modeled[column] = raw[column].astype(str)
    modeled["BMXBMI"] = pd.cut(
        raw["BMXBMI"], bins=BMI_BINS, labels=BMI_STATES, right=False
    ).astype(str)
    return modeled


def category_mappings(raw):
    return {
        column: dict(enumerate(raw[column].astype("category").cat.categories))
        for column in CATEGORICAL_COLUMNS
    }
