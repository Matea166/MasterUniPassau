import csv
import math
import operator
import re
from pathlib import Path


TABLES = {"wetgrass": "wetgrass_data", "market_basket": "transactions", "nhanes": "nhanes_data"}
BMI_BINS = [(0, 18.5), (18.5, 25), (25, 30), (30, 150)]
OPERATORS = {"=": operator.eq, ">=": operator.ge, "<": operator.lt}


def query_filters(sql, dataset, raw, modeled):
    match = re.fullmatch(r"\s*SELECT\s+\*\s+FROM\s+(\w+)\s+WHERE\s+(.+?)\s*;?\s*", sql, re.I)
    if match is None or match[1].lower() != TABLES[dataset]:
        raise ValueError(f"Expected a selection from {TABLES[dataset]}.")
    raw_columns = {column.lower(): column for column in raw.columns}
    model_columns = {column.lower(): column for column in modeled.columns}
    conditions = {}
    for clause in re.split(r"\s+AND\s+", match[2], flags=re.I):
        condition = re.fullmatch(r"(\w+)\s*(>=|<|=)\s*('[^']*'|-?\d+(?:\.\d+)?)", clause)
        if condition is None:
            raise ValueError(f"Unsupported predicate: {clause}")
        column, comparison, literal = condition.groups()
        column = column.lower()
        if column not in raw_columns or column not in model_columns:
            raise ValueError(f"Unmodeled column: {column}")
        value = literal[1:-1] if literal.startswith("'") else float(literal)
        conditions.setdefault(column, []).append((comparison, value))
    filters = {}
    for column, predicates in conditions.items():
        if dataset == "nhanes" and column == "bmxbmi":
            if any(comparison not in (">=", "<") or isinstance(value, str) for comparison, value in predicates):
                raise ValueError("BMI predicates must select a complete BMI group.")
            lower = max((value for comparison, value in predicates if comparison == ">="), default=-math.inf)
            upper = min((value for comparison, value in predicates if comparison == "<"), default=math.inf)
            overlapping = [(left, right) for left, right in BMI_BINS if max(left, lower) < min(right, upper)]
            if len(overlapping) != 1 or lower > overlapping[0][0] or upper < overlapping[0][1]:
                raise ValueError("BMI predicates must select one complete BMI group.")
        elif any(comparison != "=" for comparison, _ in predicates):
            raise ValueError(f"Only equality predicates are supported for {column}.")
        raw_column, model_column = raw_columns[column], model_columns[column]
        mask = raw[raw_column].notna()
        for comparison, value in predicates:
            mask &= OPERATORS[comparison](raw[raw_column], value)
        states = modeled.loc[mask, model_column].unique()
        if len(states) != 1:
            raise ValueError(f"Predicate does not identify one observed state of {column}.")
        state = states[0]
        if not mask.equals(modeled[model_column].eq(state)):
            raise ValueError(f"Raw and modeled predicates differ for {column}.")
        filters[model_column] = state.item() if hasattr(state, "item") else state
    return filters


def load_queries(dataset, raw, modeled, path=None):
    if not raw.index.equals(modeled.index):
        raise ValueError("Raw and modeled data must have the same row index.")
    path = Path(path) if path is not None else Path(__file__).resolve().parents[1] / "workloads" / f"{dataset}.csv"
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [row["query_id"] for row in rows]
    if not rows or any(not query_id.strip() for query_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("Workload query IDs must be unique and nonempty.")
    return [(row["sql"], query_filters(row["sql"], dataset, raw, modeled)) for row in rows]
