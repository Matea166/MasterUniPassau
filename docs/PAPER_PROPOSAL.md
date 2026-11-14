# Paper proposal

Draft for discussion. The abstract must be updated with measured findings after
the full classical and hardware experiments.

## Proposed title

AnnealBN-CE: Evaluating QUBO-Based Bayesian Network Learning for Cardinality Estimation

## Abstract

Cardinality estimation remains challenging when selection predicates involve
dependencies that conventional statistics approximate poorly. Bayesian networks
provide a dependency-aware representation, but learning their structure requires
searching a combinatorial space. We present AnnealBN-CE, a framework connecting
QUBO-based Bayesian network structure learning with single-relation cardinality
estimation. A common objective supports simulated annealing, simulated quantum
annealing and gate-based QAOA, while fitted networks answer selection predicates
through probabilistic inference. Our evaluation compares the resulting estimates
with PostgreSQL and a tree-based estimator on controlled synthetic data, survey
records and a TPC-DS-derived retail sample. We examine query-level accuracy,
variation across learned structures and the computational resources required by
the solvers. An additional experiment is planned to compare ideal QAOA simulation
with IBM hardware sampling of simulator-trained circuits. The study investigates
when learned structures improve downstream estimates and which practical limits
arise when executing the same formulation on gate-based hardware.

## Contributions

1. An end-to-end adaptation of existing QUBO-based structure learning to
   single-relation cardinality estimation, preserving equivalent query semantics
   across data representations.
2. A shared QUBO interface for SA, SQA and QAOA, with an Aer implementation and
   an IBM sampling path using locally trained parameters.
3. An evaluation of complete estimators against PostgreSQL and the adapted
   Halford tree, examining both accuracy and whether graph diversity translates
   into estimation variability.
4. A reproducible artifact containing fixed workloads, data provenance,
   configurations, validation checks and solver execution metadata.

The QUBO formulation, SA/SQA algorithms and QAOA are inherited methods. Hardware
capability is a planned evaluation component, not a claim of quantum advantage.

## Organization and page budget

| Section | Pages | Focus |
|---|---:|---|
| Title, abstract and Introduction | 2.0 | Database problem, motivation, gap, contributions and structure |
| Preliminaries | 0.75 | Cardinality as probability; finite-state BNs; QUBO; SA/SQA versus QAOA |
| Related Work | 0.5 | BN estimators, annealing-based BNSL and gate-based database optimization |
| Approach | 1.25 | Shared representation and QUBO, solver interfaces, DAG decoding, fitting and inference |
| Evaluation | 2.75 | Questions, workload, setup, environment, accuracy, stability and hardware feasibility |
| Discussion and Conclusion; Acknowledgments | 0.75 | Answers, limits, next step and acknowledgments |

References are outside the eight-page allowance. The introduction ends by page 2.

## Evaluation questions

- When do the evaluated estimators differ in accuracy across the diagnostic
  workloads, and which predicate combinations explain those differences?
- How do solver budgets affect graph diversity and downstream estimate stability?
- On the instances that fit the available resources, how does IBM sampling of
  Aer-trained QAOA circuits compare with ideal sampling in QUBO energy, valid-DAG
  production and cardinality accuracy?

The third question concerns gate-based execution of a shared objective. It does
not establish hardware optimization of QAOA parameters or a quantum speedup.

## Hardware experiment

Start with the four-attribute WetGrass instance. The unchanged encoding requires
26 qubits, compared with 57 for Market Basket and 100 for TPC-DS. Assess compiled
depth and two-qubit gates before selecting a larger instance. Choose the backend,
available QPU allocation, circuit depth, shots and repetitions with the provider.

Use paired Aer and IBM runs with identical data, QUBO, initialization seed,
optimizer budget, depth and shots. Retain seeds, angles, versions, input hashes,
job IDs, compiled circuit sizes and sampled outcomes. Report QUBO energy and
cardinality accuracy separately; a better optimization objective does not
automatically imply a better cardinality estimate. Compare total sampling and
optimization effort explicitly rather than equating QAOA shots with SA/SQA reads.

If the intended experiment optimizes angles on IBM hardware at every iteration,
extend the current adapter and agree an explicit QPU budget before executing it.
