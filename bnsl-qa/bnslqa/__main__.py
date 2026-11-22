import argparse
from random import choices
import bnslqa.generators.mhp_legacy as mhp_legacy
import bnslqa.generators.generator as gen

def main():
  parser = argparse.ArgumentParser(description='Implementation of Bayesian Network Structure Learning using Quantum Annealing',
                                   prog='python -m bnslqa')
  subparsers = parser.add_subparsers(help='sub-command help')

  solver_parser = subparsers.add_parser('solve', help='estimate BN structure from data',
                                        description='',
                                        epilog='''Example: \'python -m bnslqa solve qa-datasets/WasteExp.txt QA -r 10000 -a 99\'
                                        will use D-Wave\'s Quantum Annealer to solve the WasteExp problem, with 10000 reads
                                        each with an annealing time of 99 microseconds''')
  solver_parser.add_argument('dataset', type=str, help='dataset path')
  solver_parser.add_argument('strategy', type=str, choices=['SA','QA','SQA','QAOA'],
                             help='solver strategy')
  solver_parser.add_argument('-r','--reads', type=int, metavar='NUM', default=10**4,
                             help='number of reads for annealing strategies, SA has no limits, QA can have at most 10000 [default: 10000]')
  solver_parser.add_argument('-a','--anneal', type=int, metavar='T', default=99,
                             help='annealing time in microseconds for each read (only for QA), up to 2000 [default: 99]')
  solver_parser.add_argument('--shots', type=int, default=1024, help='QAOA training shots per evaluation')
  solver_parser.add_argument('--final-shots', type=int, help='QAOA final sampling shots [default: same as --shots]')
  solver_parser.add_argument('--reps', type=int, default=1, help='QAOA circuit layers')
  solver_parser.add_argument('--maxiter', type=int, help='QAOA optimizer evaluation budget [default: SciPy COBYLA default]')
  solver_parser.add_argument('--seed', type=int, default=42, help='QAOA simulator and optimizer seed')
  solver_parser.add_argument('--qaoa-backend', choices=['aer','ibm'], default='aer')
  solver_parser.add_argument('--ibm-backend', help='IBM backend name; defaults to the least-busy suitable backend')
  solver_parser.add_argument('--ibm-api-key-file', type=str, help='file containing the IBM API key')
  solver_parser.add_argument('--ibm-instance', help='IBM Quantum compute instance CRN')
  solver_parser.add_argument('--qaoa-output', help='QAOA result JSON path')
  solver_parser.add_argument('--dry-run', action='store_true', help='report QAOA resources without execution')

  generator_parser = subparsers.add_parser('generate',
                                           help='generate problem dataset',
                                           description='Generate a dataset for a specific problem',
                                           epilog='''Example: \'python -m bnslqa generate problems/Waste.json --size 10000 --expected\'
                                           will generate an expected dataset of size 10000 for the problem Waste
                                           as qa-datasets/WasteExp.txt''')
  generator_parser.add_argument('problem', type=str,
                                help='path to the json file defining the problem')
  generator_parser.add_argument('-s', '--size', default=10**4, type=int,
                                help='number of examples (BN variables settings) to generate [default: 10000]')
  generator_parser.add_argument('-e', '--expected', action='store_true',
                                help='generate a dataset with expected values (no variance)')
  generator_parser.add_argument('-n', '--name', default=None, type=str,
                                help='dataset name, will be saved in qa-datasets/NAME.txt [default: based on parameters and problem definition]')
  generator_parser.add_argument('-l', '--legacy', action='store_true',
                                help='MHP only: generate the dataset the same way as used for the original experiments. Note: this already the case for the other problems')
  generator_parser.set_defaults(func=gen.main)
  generator_parser.set_defaults(parser=generator_parser)

  args = parser.parse_args()
  if getattr(args, 'dry_run', False) and args.strategy != 'QAOA':
    parser.error('--dry-run is supported only for QAOA')

  if 'func' not in args:
    if 'strategy' in args:
      if args.strategy == 'QAOA':
        from bnslqa.solvers import qaoa_solver
        args.func = qaoa_solver.main
      else:
        from bnslqa.solvers import dwave_solver
        args.func = dwave_solver.main
    else:
      parser.print_usage()
      parser.exit(1)

  if 'legacy' in args:
    if args.legacy:
      if 'mhp' in args.problem.lower():
        args.func = mhp_legacy.main

  if getattr(args, 'strategy', None) == 'QAOA':
    try:
      args.func(args)
    except qaoa_solver.InvalidGraphError as error:
      parser.exit(3, f'{error}\n')
  else:
    args.func(args)

if __name__ == '__main__':
  main()
