#!/usr/bin/env python3
"""Drive the full focused eval: triggers + grading for every skill in config, then the
scorecard. Skills run sequentially; each stage is internally concurrent, so the
number of live `claude -p` processes stays bounded by --concurrency.

    python evals/harness/run_all.py [--concurrency K] [--limit N] [--repeats R]
                                    [--skip-triggers] [--skip-grading]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import aggregate
import grade_tasks
import run_triggers

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    cfg = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
    ap = argparse.ArgumentParser(description='Full focused skill eval')
    ap.add_argument('--concurrency', type=int, default=6)
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--repeats', type=int, default=None)
    ap.add_argument('--skip-triggers', action='store_true')
    ap.add_argument('--skip-grading', action='store_true')
    args = ap.parse_args()
    skills = sorted(cfg['plugin_of_skill'])

    def argv_for(skill):
        a = [skill, '--concurrency', str(args.concurrency)]
        if args.limit:
            a += ['--limit', str(args.limit)]
        if args.repeats:
            a += ['--repeats', str(args.repeats)]
        return a

    t0 = time.time()
    if not args.skip_triggers:
        for s in skills:
            print(f'\n========== TRIGGERS: {s} ==========', flush=True)
            run_triggers.main(argv_for(s))
    if not args.skip_grading:
        for s in skills:
            print(f'\n========== GRADING: {s} ==========', flush=True)
            grade_tasks.main(argv_for(s))

    print('\n========== SCORECARD ==========', flush=True)
    aggregate.main([])
    print(f'\nALL DONE in {(time.time() - t0) / 60:.1f} min', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
