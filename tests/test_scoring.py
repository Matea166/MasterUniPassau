from collections import Counter
import itertools
import math
import tempfile
import unittest
from pathlib import Path

from bnslqa.solvers import qubo_values as qubo
from bnslqa.solvers.solver_utils import getNumExamples


class ScoringTests(unittest.TestCase):
    def test_heterogeneous_domain_scores_match_independent_counts(self):
        states = [2, 3, 4]
        examples = [list(row) for row in itertools.product(*(range(n) for n in states))]
        examples += [[0, 1, 3]] * 7 + [[1, 2, 0]] * 3
        parent_sets = qubo.calcParentSets(3)
        alphas = qubo.calcAlpha(3, states, parent_sets, len(examples))
        for child, parents in ((i, parents) for i in range(3) for parents in parent_sets[i]):
            with self.subTest(child=child, parents=parents):
                totals = Counter(tuple(row[p] for p in parents) for row in examples)
                counts = Counter((tuple(row[p] for p in parents), row[child]) for row in examples)
                qi = math.prod(states[p] for p in parents)
                alpha = 1 / (states[child] * qi)
                score = 0
                for setting in itertools.product(*(range(states[p]) for p in parents)):
                    score += math.lgamma(states[child] * alpha) - math.lgamma(states[child] * alpha + totals[setting])
                    score += sum(math.lgamma(alpha + counts[setting, k]) - math.lgamma(alpha)
                                 for k in range(states[child]))
                self.assertAlmostEqual(qubo.calcSi(child, parents, states, alphas, examples), -score, places=10)

    def test_example_count_excludes_all_three_header_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "dataset.txt"
            source.write_text("2 2 2\nfixture\n0 0\n0 1\n1 0\n")
            self.assertEqual(getNumExamples(source), 2)


if __name__ == "__main__":
    unittest.main()
