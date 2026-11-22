# This file is based on code from BNSL-QA-PYTHON.
# Original project licensed under the GNU General Public License, Version 2.
# Modified by Matea Qazolli, 2026.
# Modifications include package import adaptation, simulated quantum annealing
# support, QUBO matrix output,
# solver-routing logic, timing handling, and experiment workflow adaptations.

from time import time_ns
import os
import torch
import networkx as nx
from .qubo_matrix import calcQUBOMatrix, printMatrix
from .solver_utils import getExpectedSolution, printInfoResults, getNumExamples, getData

from dimod.reference.samplers import ExactSolver
from neal import SimulatedAnnealingSampler
from dwave.system import DWaveSampler, EmbeddingComposite
from dwave.samplers import PathIntegralAnnealingSampler

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

    minXt, minY, readFound, occurrences, annealTimeRes = dwaveSolve(
        Q, indexQUBO, posOfIndex, label,
        method=method, nReads=nReads, annealTime=annealTime
    )

    graph = nx.DiGraph(
        (index[1], index[2])
        for index, value in zip(indexQUBO, minXt)
        if index[0] == 'd' and value == 1
    )
    if not nx.is_directed_acyclic_graph(graph) or any(degree > 2 for _, degree in graph.in_degree()):
        return

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
