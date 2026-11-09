import argparse
import csv
import hashlib
import io
import json
import random
from decimal import Decimal
from pathlib import Path


def verify(data, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("TPC-DS checksum does not match the recorded dataset.")


def main():
    data_dir = Path(__file__).resolve().parent / "data"
    metadata = json.loads((data_dir / "TPCDS_store_sales_10000.json").read_text())
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--output", type=Path, default=data_dir / "TPCDS_store_sales_10000.csv")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        if args.source:
            parser.error("Use either a source file or --check.")
        verify(args.output.read_bytes(), metadata["sample_sha256"])
        print("TPC-DS sample checksum verified.")
        return
    if args.source is None:
        parser.error("Provide store_sales.dat, or use --check to verify the CSV.")
    digest = hashlib.sha256()
    total = 0
    with args.source.open("rb") as handle:
        for line in handle:
            digest.update(line)
            total += 1
    if total != metadata["source_rows"] or digest.hexdigest() != metadata["source_sha256"]:
        raise ValueError("Source file does not match the recorded TPC-DS generation.")
    chosen = set(random.Random(metadata["sample_seed"]).sample(range(total), metadata["sample_rows"]))
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([column["name"] for column in metadata["columns"]])
    with args.source.open() as handle:
        for index, line in enumerate(handle):
            if index not in chosen:
                continue
            fields = line.rstrip("\n").split("|")
            if len(fields) != 24 or fields[-1] != "":
                raise ValueError("Expected 23 pipe-delimited fields and a trailing delimiter.")
            row = []
            for column in metadata["columns"]:
                value = fields[column["source_position"] - 1]
                if value:
                    value = str(int(value)) if column["type"] == "INTEGER" else format(Decimal(value), ".2f")
                row.append(value)
            writer.writerow(row)
    data = output.getvalue().encode("utf-8")
    verify(data, metadata["sample_sha256"])
    args.output.write_bytes(data)
    print(f"Wrote {metadata['sample_rows']} verified TPC-DS rows to {args.output}.")


if __name__ == "__main__":
    main()
