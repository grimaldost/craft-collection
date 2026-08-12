# Non-vacuity procedures

Candidate reference for `verification-before-completion`, holding the procedures
displaced out of the body. Each bright line stays in the body; what moved here is
how to carry it out. Not shipped — see `../../README.md` for what has to be true
before it is.

## Reading an exit code after a pipe

`$?` is the **last** command's exit code, so a pipeline reports the exit status
of the tail, not of the thing you wanted to prove. `pytest | tee out.txt`
succeeds whenever `tee` succeeds. Read `$?` right after the bare command, or
capture output to a file and read the file:

```sh
pytest > out.txt 2>&1; echo "exit=$?"; tail -20 out.txt
```

`set -o pipefail` fixes the shell case but not the habit, and not every runner is
a shell.

## Removing a plant by the inverse edit

Plant a known violation, confirm the catch, then undo the plant **by the inverse
edit** — retype the original bytes, or apply the reverse patch. A checkout of the
file also discards whatever else was in it, including the work you were
verifying, and it silently succeeds either way. Only a byte-precise restore is
itself verifiable: diff against the pre-plant state and require an empty diff.

The same holds for the red half of a red-green cycle. Reverting the fix to watch
a regression test fail is an inverse edit of the fix, not a checkout of the file
the fix lives in.

One trap worth naming, because it manufactures lift out of nothing: reverting
*new* code often makes a test **error** — an import or collection failure —
rather than fail. An error is not a red. A verifier that scores it as one is
measuring whether the file parses.

## Capturing a zero-net-regression baseline

When the suite carries irreducible pre-existing failures, the honest gate is the
difference between two failure sets, not an absolute zero:

1. Capture the baseline — stash the change and run the suite, or run it at the
   base commit. Save the failure set, not the count.
2. Run the suite with the change. Save that failure set.
3. Require `after - before` to be empty. A test that was already failing stays
   failing; a new name in the difference is a regression, whatever the totals do.

Counts alone hide the case that matters: one test fixed and one broken nets to
zero.

## How a check comes to test nothing

A green check is compatible with several states that are not "the property
holds":

- **An empty scan.** Zero files matched, zero rows read, zero cases collected.
  The check passes and gets quoted as evidence. This is the worst one, because
  the output looks identical to a real pass.
- **A predicate nothing can trip.** A typo'd join key that matches nothing, a
  tolerance wider than any real deviation, an assertion on a value the code
  cannot produce.
- **A fixture that hits a fallback.** The path under test is never entered; a
  default, a cached value, or a stub answers instead.
- **A runner that collects nothing.** A module of pytest fixtures run under bare
  `python` collects zero tests, prints nothing, exits 0. A suite that reports
  PASS over it has a disconnected safety net and no way to know.

So a check reports **how many units it saw**, and zero is a failure — not a
convention, a return code. That is the mechanized form of "count the files, rows,
or cases it saw"; `scripts/run_tests.py` in this repository is one implementation
(a module that exits 0 without a sentinel fails the suite, proven by a fixture
that does exactly that).

## Where the fuller matrix lives

`data-engineering-discipline`, when installed, carries the canonical non-vacuity
matrix for data checks — per-check counts of rows read, keys matched and cases
exercised, with the failure mode each count catches.
