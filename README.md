# AnnealBN-CE

Research code for a planned submission to the [BTW 2027 Student Program](https://btw2027.gi.de/calls/student-program),
extending a [master's thesis at the University of Passau](docs/Master%20Thesis.pdf).
The experiments compare cardinality estimates from annealing-learned Bayesian
networks, a tree baseline and PostgreSQL on fixed single-table workloads.

Structure learning uses simulated annealing (SA) and simulated quantum annealing
(SQA). The tree retains the normalized mutual information implementation from
[tldks-2020](https://github.com/MaxHalford/tldks-2020). PostgreSQL uses ordinary
statistics after `ANALYZE`.

QAOA supports noiseless Qiskit Aer and IBM hardware sampling; see the
[IBM smoke-test setup](#ibm-quantum-smoke-test) below and the
[usage guide](docs/USAGE.md#qaoa).

## Run the experiments

Install and start Docker Desktop. Python and PostgreSQL run inside Docker.

```bash
git clone --branch btw2027 https://github.com/Matea166/MasterUniPassau.git
cd MasterUniPassau
QUICK=0 ./reproduce_all.sh
```

On Windows, run `.\reproduce_all.bat` from the cloned folder with `QUICK=0`.
See the [usage guide](docs/USAGE.md#running-experiments) for platform commands
and individual experiments.

The default run recreates this project's Docker database volume. Set `FRESH=0`
to keep the volume; experiment tables are still reloaded. Allow several hours
for the full run. On macOS, keep the machine awake with:

```bash
caffeinate -i env QUICK=0 ./reproduce_all.sh
```

For a smaller workflow check:

```bash
QUICK=1 ./reproduce_all.sh
```

Quick mode reduces the WetGrass, NHANES and Market Basket configuration grids
and the random-structure check. TPC-DS uses the same fixed settings in both modes:
SA and SQA each use 5 trials × 500 reads.

## IBM Quantum smoke test

Start Docker and follow these steps from the cloned repository's root directory.
Credentials are supplied through an external file; no Qiskit account-saving step
is needed.

1. Create an API-key file **outside the repository**.

   **macOS/Linux:**

   ```bash
   mkdir -p "$HOME/.config/annealbn-ce"
   touch "$HOME/.config/annealbn-ce/ibm_api_key.txt"
   chmod 600 "$HOME/.config/annealbn-ce/ibm_api_key.txt"
   ```

   `chmod 600` allows only the file owner to read or write it. Open the file in a
   local editor, paste only your IBM Cloud API key, and save it.

   **Windows (PowerShell):**

   ```powershell
   $ibmKeyDir = Join-Path $env:USERPROFILE ".config\annealbn-ce"
   New-Item -ItemType Directory -Force -Path $ibmKeyDir | Out-Null
   $ibmKeyFile = Join-Path $ibmKeyDir "ibm_api_key.txt"
   New-Item -ItemType File -Path $ibmKeyFile | Out-Null
   $ibmIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
   icacls $ibmKeyFile /inheritance:r /grant:r "${ibmIdentity}:(R,W)"
   notepad $ibmKeyFile
   ```

   For this newly created file, `icacls` removes inherited access permissions
   and grants your Windows user read/write access. Paste only your IBM Cloud
   API key into Notepad, save the file, and close it.

2. Copy the settings template once, if `.env` does not already exist:

   ```bash
   cp .env.example .env
   ```

   In Windows PowerShell, use:

   ```powershell
   Copy-Item .env.example .env
   ```

   Edit `.env` with the key file's **absolute path** and your IBM instance CRN:

   ```dotenv
   IBM_API_KEY_FILE=/absolute/path/to/ibm_api_key.txt
   IBM_INSTANCE=your-instance-crn
   IBM_BACKEND=
   ```

   On Windows, use forward slashes and quote the absolute path, for example:

   ```dotenv
   IBM_API_KEY_FILE="C:/Users/YourName/.config/annealbn-ce/ibm_api_key.txt"
   ```

   Leave `IBM_BACKEND` empty to select the least-busy suitable IBM backend, or
   enter a specific backend name. These settings are reused on later runs.
   `.env` contains the key's path, not the key itself, and is excluded from Git
   and the Docker build context.

3. Build and run the smoke test. This command is the same in macOS/Linux shells
   and Windows PowerShell:

   ```bash
   docker compose -f docker-compose.quantum.yml run --build --rm quantum
   ```

   This uses ten WetGrass rows and the Rain/WetGrass attributes. QAOA parameters
   are optimized locally with noiseless Aer and COBYLA, followed by one IBM
   hardware job for final sampling. Results, logs and a ZIP archive are saved
   under `results/ibm/`.

Docker mounts the key file read-only at `/run/secrets/ibm_api_key` when the
container runs. The key is not baked into the image. The original key file on
your computer remains unencrypted; keep its permissions restricted.

## Data and results

| Dataset | Rows | Modeled attributes |
|---|---|---|
| WetGrass | 100 and 10,000 | 4 |
| NHANES | 2,278 | 4 |
| Market Basket | 100 and 10,000 | 6 |
| TPC-DS `store_sales` sample | 10,000 | 8 |

Each dataset has [20 queries](workloads/). WetGrass and Market Basket are generated
with fixed settings; NHANES and TPC-DS CSVs are included. No dataset download is
needed for a normal run. The TPC-DS experiment uses a research sample and custom
queries; it is not an official TPC-DS benchmark result.

Open `results/index.html` after a run. It contains estimates, clamped q-error
summaries and comparison charts, with CSV downloads. Logs and per-structure
estimates are stored under `results/<experiment>/`.

See the usage guide for [data and grouping](docs/USAGE.md#datasets),
[metrics](docs/USAGE.md#metrics) and [output files](docs/USAGE.md#outputs).
Saved PostgreSQL measurements and input hashes are in [reference_results/](reference_results/).

## Checks

```bash
docker compose run --build --rm --no-deps app python -m unittest discover -s tests -v
```

The expanded workflow is awaiting full end-to-end validation. SA and SQA are
stochastic, so structures and estimates can vary between runs.

## Licence and sources

The project includes code adapted from
[BNSL-QA-python](https://github.com/massimo-rizzoli/BNSL-QA-python) and
[tldks-2020](https://github.com/MaxHalford/tldks-2020).
See [LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md) and
[THIRD_PARTY_LICENSES/](THIRD_PARTY_LICENSES/) for attribution and licence terms.
