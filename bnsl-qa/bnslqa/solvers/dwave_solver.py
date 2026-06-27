## Modified Python file derived from BNSL-QA-PYTHON

```python
# This file is based on code from BNSL-QA-PYTHON.
# Original project licensed under the GNU General Public License, Version 2.
# Modified by Matea Qazolli, 2026.
# Modifications include Docker integration, PostgreSQL connectivity,
# logging/output changes, and experiment workflow adaptations.
```

from time import time_ns
import os
import torch
from .qubo_matrix import calcQUBOMatrix, printMatrix
from .solver_utils import getExpectedSolution, printInfoResults, getNumExamples, getData

from dimod.reference.samplers import ExactSolver
from neal import SimulatedAnnealingSampler
from dwave.system import DWaveSampler, EmbeddingComposite
from dwave.samplers import PathIntegralAnnealingSampler

# --- NEW QRISP & IBM IMPORTS ---
from qrisp import QuantumVariable
from qrisp.algorithms.qaoa import QAOAProblem
from qrisp.interface import QiskitBackend
from qiskit_ibm_runtime import QiskitRuntimeService


# -------------------------------


def getDwaveQubo(Q, indexQUBO):
    qubo = {}
    for i in range(len(indexQUBO)):
        for j in range(i, len(indexQUBO)):
            if Q[i][j] != 0:
                qubo[(indexQUBO[i], indexQUBO[j])] = Q[i, j].item()
    return qubo


def getSampler(method='SA'):
    sampler = None
    if method == 'SA':
        sampler = SimulatedAnnealingSampler()
    elif method == 'QA':
        sampler = EmbeddingComposite(
            DWaveSampler(
                profile=os.getenv('DWAVE_PROFILE'),
                solver={'topology__type__eq': 'pegasus'}
            )
        )
    elif method == 'SQA':
        sampler = PathIntegralAnnealingSampler()
    else:
        sampler = ExactSolver()
    return sampler


def getMinXt(bestSample, indexQUBO, posOfIndex):
    minXt = torch.zeros(len(indexQUBO))
    for index, value in bestSample.items():
        pos = posOfIndex[index]
        minXt[pos] = value
    return minXt


def getMinInfo(record):
    readFound = None
    occurrences = None
    minEnergy = float('inf')
    for i, (_, energy, occ, *_) in enumerate(record):
        if energy < minEnergy:
            minEnergy = energy
            occurrences = occ
            readFound = i
    return readFound, occurrences


def writeCSV(n, probName, alpha, method, nReads, annealTime,
             dsName, calcQUBOTime, annealTimeRes, readFound,
             occurrences, minY, expY, minXt, path):
    with open('./tests/tests_anneal.csv', 'a') as file:
        examples = getNumExamples(path)
        if method != 'QA':
            annealTime = '-'
        template = '{},' * 12 + ',,' + '{},' * 2 + '\'{}\'' + '\n'
        testResult = template.format(
            n, probName, alpha, examples, method, nReads, annealTime,
            dsName, calcQUBOTime / 10 ** 6, annealTimeRes / 10 ** 6,
            readFound, occurrences, minY, expY, minXt.int().tolist()
        )
        file.write(testResult)


def dwaveSolve(Q, indexQUBO, posOfIndex, label, method='SA', nReads=1000, annealTime=99):
    qubo = getDwaveQubo(Q, indexQUBO)
    sampler = getSampler(method=method)
    startAnneal = time_ns()

    if method == 'QA':
        # Hardware: uses annealing_time in microseconds
        sampleset = sampler.sample_qubo(qubo, num_reads=nReads, label=label, annealing_time=annealTime)

    elif method == 'SQA':
        # Simulation: uses sweeps and beta schedules to emulate quantum thermalization
        sampleset = sampler.sample_qubo(
            qubo,
            num_reads=nReads,
            num_sweeps=1000,
            beta_schedule_type='geometric',
            label=label
        )

    else:
        # Classical SA
        sampleset = sampler.sample_qubo(qubo, num_reads=nReads, label=label)

    endAnneal = time_ns()

    if 'timing' in sampleset.info.keys() and method == 'QA':
        print(sampleset.info['timing'])
        annealTimeRes = sampleset.info['timing'].get('qpu_access_time', (endAnneal - startAnneal) // 10 ** 3)
    else:
        # Fixed the 103 typo here to 10**3
        annealTimeRes = (endAnneal - startAnneal) // 10 ** 3

    minXt = getMinXt(sampleset.first.sample, indexQUBO, posOfIndex)
    minX = minXt.view(-1, 1)
    minY = torch.matmul(torch.matmul(minXt, Q), minX).item()
    readFound, occurrences = getMinInfo(sampleset.record)

    return minXt, minY, readFound, occurrences, annealTimeRes


# --- NEW QRISP SOLVER FUNCTION ---
def qrispSolve(Q, indexQUBO, method='QRISP_SIM', nReads=1000, p=1):
    num_vars = len(indexQUBO)

    def cost_operator(qv):
        for i in range(num_vars):
            for j in range(i, num_vars):
                weight = Q[i, j].item()
                if weight != 0:
                    if i == j:
                        qv.phase(weight, i)
                    else:
                        qv.phase(weight, [i, j])

    qaoa_p = QAOAProblem(cost_operator, p=p)
    start_time = time_ns()

    print("Optimizing QAOA parameters locally...")
    res_sim = qaoa_p.run(max_iter=50)

    if method == 'QRISP_HW':
        print("Connecting to real quantum hardware...")
        service = QiskitRuntimeService()
        backend = service.least_busy(operational=True, simulator=False)
        print(f"Executing on QPU: {backend.name}")

        qrisp_hw_backend = QiskitBackend(backend)
        qpu_results = qaoa_p.get_measurement(
            backend=qrisp_hw_backend,
            shots=nReads
        )
        results_to_process = qpu_results
    else:
        results_to_process = res_sim

    end_time = time_ns()
    qaoa_time_res = (end_time - start_time) // 10 ** 3

    best_sample = max(results_to_process, key=results_to_process.get)
    occurrences = results_to_process[best_sample] * nReads if isinstance(results_to_process[best_sample], float) else \
    results_to_process[best_sample]

    minXt = torch.tensor([int(bit) for bit in best_sample])
    minX = minXt.view(-1, 1).float()
    minY = torch.matmul(torch.matmul(minXt.float(), Q.float()), minX).item()

    readFound = 0

    return minXt, minY, readFound, int(occurrences), qaoa_time_res


# ---------------------------------


def main(args):
    startCalcQUBO = time_ns()
    path = args.dataset
    method = args.strategy
    nReads = args.reads
    annealTime = args.anneal

    # Calculate the QUBO matrix given the dataset path
    alpha = '1/(ri*qi)'
    examples, n, states, problemName, solution = getData(path)
    Q, indexQUBO, posOfIndex = calcQUBOMatrix(examples, n, states, alpha=alpha)
    from bnslqa.solvers.qubo_matrix import printMatrix

    print("\nQUBO Matrix:")
    printMatrix(Q, indexQUBO)
    Q = torch.tensor(Q)

    # Calculate the expected solution value
    expXt, expY = getExpectedSolution(solution, Q, indexQUBO, posOfIndex, n)
    endCalcQUBO = time_ns()
    calcQUBOTime = (endCalcQUBO - startCalcQUBO) // 10 ** 3

    # Find minimum of the QUBO problem xt Q x using the specified sampler
    dsName = path[path.find('/') + 1:path.find('.')]
    label = '{} - {} reads'.format(dsName, nReads)

    # --- ROUTING LOGIC ---
    if method in ['QRISP_SIM', 'QRISP_HW']:
        minXt, minY, readFound, occurrences, annealTimeRes = qrispSolve(
            Q, indexQUBO, method=method, nReads=nReads
        )
    else:
        minXt, minY, readFound, occurrences, annealTimeRes = dwaveSolve(
            Q, indexQUBO, posOfIndex, label,
            method=method, nReads=nReads, annealTime=annealTime
        )
    # ---------------------

    printInfoResults(expXt, expY, minXt, minY, n)
    print(
        'Method: {}\nNumber of reads: {}\nOccurrencies of minX: {}\nFound minX at read: {}\n'
        'QUBO formulation time: {}\nAnnealing/Execution time: {}'.format(
            method, nReads, occurrences, readFound,
            calcQUBOTime / 10 ** 6, annealTimeRes / 10 ** 6
        )
    )

    # Write data to CSV file
    writeCSV(
        n, problemName, alpha, method, nReads, annealTime,
        dsName, calcQUBOTime, annealTimeRes, readFound,
        occurrences, minY, expY, minXt, path
    )
