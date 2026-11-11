import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bnsl.datasets.grouping_tpcds import (
    DATA_PATH,
    SOLVER_PATH,
    encode,
    write_solver_input,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DATA_PATH)
    parser.add_argument("--output", type=Path, default=SOLVER_PATH)
    args = parser.parse_args()
    encoded = encode(pd.read_csv(args.input))
    write_solver_input(encoded, args.output)
    print(f"Encoded {len(encoded)} rows to {args.output}.")


if __name__ == "__main__":
    main()
