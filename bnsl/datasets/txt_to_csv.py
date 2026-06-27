import csv

# =========================
# CONFIG
# =========================
input_txt_file = "../../bnsl-qa/qa-datasets/WetGrass.txt"
output_csv_file = "data/WetGrass_variance_zero.csv"


columns = ["Cloud", "Sprinkler", "Rain", "WetGrass"]

state_maps = {
    "Cloud": {0: "t", 1: "f"},
    "Sprinkler": {0: "on", 1: "off"},
    "Rain": {0: "t", 1: "f"},
    "WetGrass": {0: "t", 1: "f"}
}


data_rows = []

with open(input_txt_file, "r") as f:
    lines = f.readlines()

for line in lines[2:]:
    line = line.strip()
    if not line:
        continue
    values = list(map(int, line.split()))
    if len(values) != len(columns):
        print(f"[Warning] Line skipped due to length mismatch: {line}")
        continue

    mapped_values = [state_maps[col][val] for col, val in zip(columns, values)]
    data_rows.append(mapped_values)


with open(output_csv_file, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(columns)
    writer.writerows(data_rows)

print(f"CSV file generated: {output_csv_file} with {len(data_rows)} rows")
