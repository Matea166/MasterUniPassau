# QAOA experiments

QAOA uses the existing Bayesian-network QUBO, including its auxiliary variables.
Coefficients use the same initial tensor precision as SA/SQA before conversion.
Qiskit's native QAOA ansatz maps the Ising cost operator to alternating layers.
Aer trains circuit parameters with an ideal statevector simulator and
COBYLA. The fitted circuit is sampled on Aer, or explicitly submitted to IBM
hardware. IBM mode is simulator-trained QAOA with hardware sampling; it does not
optimize parameters on the QPU. SA/SQA settings and the default full workflow
are unchanged.

## Local simulation

Rebuild the app after pulling the changes. From the repository root:

```bash
docker compose exec -T app bash scripts/prepare_datasets.sh
docker compose exec -T -w /workspace/bnsl-qa app python -m bnslqa solve qa-datasets/WetGrass.txt QAOA --dry-run
```

The full encoding needs 26 qubits for four attributes, 57 for six and 100 for
eight. Dense statevector storage alone is 1 GiB at 26 qubits, excluding simulator
overhead. The default local limit is 20 qubits. Increase it explicitly only when
the simulator has enough memory:

```bash
docker compose exec -T -w /workspace/bnsl-qa app python -m bnslqa solve qa-datasets/WetGrass.txt QAOA --max-qubits 26 --reps 1 --shots 1024 --maxiter 30 --seed 42 --qaoa-output /workspace/results/qaoa/wetgrass.json
```

These are starting settings for validation, not a tuned or equal-cost comparison
with annealing. `--reps` controls circuit layers. `--shots` applies separately to
each objective evaluation and to the final measurement. `--maxiter` is COBYLA's
evaluation budget. Metadata records the actual evaluations, versions, seeds,
angles, sample counts, QUBO energy and input hashes. The lowest-energy valid
sample is decoded to a DAG; cyclic or over-parented graphs are excluded.

To reuse the cardinality-estimation dispatcher, set `SOLVER=QAOA` with its usual
dataset and estimator arguments. `READS` supplies shots unless `QAOA_SHOTS` is
set. Options are `QAOA_REPS`, `QAOA_MAXITER`, `QAOA_SEED` and `QAOA_MAX_QUBITS`.
The seed increments across trials. JSON files go under `results/qaoa/`; set
`QAOA_RESULTS_DIR` to choose a different directory. The dispatcher runs Aer only.

## IBM hardware

Choose the backend and QPU budget with the hardware provider first. Configure
a saved Qiskit Runtime account in the execution environment using IBM's normal
account setup. Do not put tokens in the repository or Docker image. The command
below submits a real job when run in an authenticated environment:

```bash
python -m bnslqa solve qa-datasets/WetGrass.txt QAOA --max-qubits 26 --qaoa-backend ibm --ibm-backend BACKEND_NAME --reps 1 --shots 1024 --maxiter 30 --seed 42 --qaoa-output ../results/qaoa/wetgrass_ibm.json
```

Aer still trains parameters locally, so its memory limit also applies in IBM
mode. Use identical data, seed, depth, shots and optimizer budget for paired
Aer/IBM runs. Hardware metadata records the job ID before waiting for completion,
backend, compiled depth and two-qubit gate count. Actual IBM execution remains
unvalidated until a backend and account are available. Qubit count alone does
not establish hardware feasibility; routing and circuit depth must be assessed.

References: [Aer SamplerV2](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.primitives.SamplerV2.html),
[IBM SamplerV2](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/0.45/sampler-v2),
[IBM QAOA tutorial](https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm).
The tutorial also demonstrates hardware-in-the-loop parameter optimization;
our initial hardware path transfers Aer-trained parameters to one QPU sampling
job to bound QPU usage. Objective values here are calculated from sampled
bitstrings, so no observable-to-physical-layout transformation is required.
