import csv
import itertools
import math
import re
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "bnsl/datasets/data/TPCDS_store_sales_10000.csv"
WORKLOAD_PATH = ROOT / "workloads/tpcds_store_sales.csv"
SOLVER_PATH = ROOT / "bnsl-qa/qa-datasets/TPCDS_store_sales_10000.txt"
DOMAINS = {
    "ss_quantity": (1, [(1, 25), (26, 50), (51, 75), (76, 100)]),
    "ss_sales_price": (100, [(0, 2499), (2500, 4999), (5000, 9999), (10000, math.inf)]),
    "ss_coupon_amt": (100, [(0, 0), (1, 99999), (100000, math.inf)]),
    "ss_net_profit": (100, [(-math.inf, -1), (0, 99999), (100000, math.inf)]),
    "ss_wholesale_cost": (100, [(0, 2499), (2500, 4999), (5000, 7499), (7500, math.inf)]),
    "ss_net_paid": (100, [(0, 99999), (100000, 299999), (300000, math.inf)]),
    "ss_list_price": (100, [(0, 4999), (5000, 9999), (10000, math.inf)]),
    "ss_store_sk": (1, [(1, 1), (2, 2), (4, 4), (7, 7), (8, 8), (10, 10)]),
}
COLUMNS = list(DOMAINS)
STATE_NAMES = {column: list(range(len(groups) + 1)) for column, (_, groups) in DOMAINS.items()}


def encode(raw):
    encoded = pd.DataFrame(index=raw.index)
    for column, (scale, groups) in DOMAINS.items():
        values = pd.to_numeric(raw[column], errors="raise")
        scaled = values * scale
        present = scaled.dropna().to_numpy(dtype=float)
        if not np.isfinite(present).all() or not np.allclose(present, np.rint(present), rtol=0, atol=1e-7):
            raise ValueError(f"Invalid precision or nonfinite value in {column}.")
        scaled = scaled.round()
        codes = pd.Series(-1, index=raw.index, dtype=int)
        for code, (lower, upper) in enumerate(groups):
            codes.loc[scaled.between(lower, upper)] = code
        codes.loc[values.isna()] = len(groups)
        if (codes < 0).any():
            raise ValueError(f"Value outside the encoding domain of {column}.")
        encoded[column] = codes
    return encoded


def tree_state(column, code):
    return "MISSING" if code == STATE_NAMES[column][-1] else str(code)


def tree_data(encoded):
    return pd.DataFrame({column: encoded[column].map(lambda code: tree_state(column, code))
                         for column in encoded.columns}, index=encoded.index)


def query_filters(sql):
    match = re.fullmatch(r"\s*SELECT\s+\*\s+FROM\s+(?:public\.)?store_sales\s+WHERE\s+(.+?)\s*;?\s*", sql, re.I)
    if match is None:
        raise ValueError("Expected a single-table store_sales selection.")
    bounds = {}
    null_filters = {}
    for clause in re.split(r"\s+AND\s+", match[1], flags=re.I):
        null_match = re.fullmatch(r"(\w+)\s+IS\s+(NOT\s+)?NULL", clause, re.I)
        if null_match:
            column = null_match[1].lower()
            if column not in DOMAINS:
                raise ValueError(f"Unknown column: {column}")
            states = STATE_NAMES[column][:-1] if null_match[2] else STATE_NAMES[column][-1:]
            null_filters[column] = set(states) & null_filters.get(column, set(STATE_NAMES[column]))
            continue
        condition = re.fullmatch(r"(\w+)\s*(>=|<=|=|<|>)\s*(-?\d+(?:\.\d+)?)", clause)
        if condition is None or condition[1].lower() not in DOMAINS:
            raise ValueError(f"Unsupported predicate: {clause}")
        column, operator, literal = condition.groups()
        column = column.lower()
        value = Decimal(literal) * DOMAINS[column][0]
        lower, upper = bounds.get(column, (-math.inf, math.inf))
        if operator == "=":
            lower, upper = max(lower, math.ceil(value)), min(upper, math.floor(value))
        elif operator == ">=":
            lower = max(lower, math.ceil(value))
        elif operator == ">":
            lower = max(lower, math.floor(value) + 1)
        elif operator == "<=":
            upper = min(upper, math.floor(value))
        else:
            upper = min(upper, math.ceil(value) - 1)
        bounds[column] = lower, upper
    filters = {}
    for column, (lower, upper) in bounds.items():
        states = []
        for code, (left, right) in enumerate(DOMAINS[column][1]):
            if max(lower, left) > min(upper, right):
                continue
            if lower > left or upper < right:
                raise ValueError(f"Predicate cuts through a group in {column}; refine the encoding first.")
            states.append(code)
        filters[column] = states
    for column, states in null_filters.items():
        filters[column] = sorted(states & set(filters.get(column, STATE_NAMES[column])))
    return filters


def assignments(filters):
    for values in itertools.product(*filters.values()):
        yield dict(zip(filters, values))


def matching_rows(encoded, filters):
    mask = pd.Series(True, index=encoded.index)
    for column, states in filters.items():
        mask &= encoded[column].isin(states)
    return mask


def load_queries(path=WORKLOAD_PATH):
    with Path(path).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [row["query_id"] for row in rows]
    if not rows or len(set(ids)) != len(ids):
        raise ValueError("Query IDs must be unique and the workload must not be empty.")
    return [(row, query_filters(row["sql"])) for row in rows]


def write_solver_input(encoded, output=SOLVER_PATH):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as handle:
        handle.write("8 " + " ".join(str(len(STATE_NAMES[c])) for c in COLUMNS) + "\n")
        handle.write("TPCDS_store_sales_10000\n")
        handle.write(" ".join(["0"] * 56) + "\n")
        encoded[COLUMNS].to_csv(handle, sep=" ", header=False, index=False)
