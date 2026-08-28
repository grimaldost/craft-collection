# Environment traps — the same command, a different answer

A lookup table for a specific failure class: **a tool resolves differently
depending on where it was invoked from**, and the difference is silent or looks
like something else. Read it when a result contradicts a result you trust,
especially when the two came from different contexts.

What unites these is not "Windows" or "shell quoting". It is that each one
returns a *plausible* answer rather than an error, so the reader spends the next
several minutes debugging the wrong thing. Each entry names the signature that
identifies it fast.

| Trap | What happens | The signature |
|------|--------------|---------------|
| `Glob` with an explicit non-cwd `path` | Returns "No files found" for files that exist. Recurred four-plus times across the corpus before it was written down. | A negative result for a path you can `ls`. Never act on a `Glob` negative outside the cwd — confirm with `ls` first. |
| Background shell vs interactive shell `PATH` | `shutil.which('bash')` resolves to a different binary. One battery ran 22/22 green interactively and 4 FAILED exit 127 in a background driver, because `PATH` found the WSL `bash` (which rejects Windows paths) instead of Git's. | **Untouched files go red too.** A regression touches what changed; a resolution fault reddens the innocent. Prepend the intended toolchain to the driver's `PATH`. |
| Non-ASCII text through a heredoc | A heredoc carrying accented prose or arrows fails to parse, or the escapes arrive interpreted. Three occurrences across two sessions, each costing a retry. | `unexpected EOF while looking for matching quote`, or escape sequences that became real newlines. Write the block to a file and concatenate, or use the harness's own write tool. Do not fight the quoting. |
| UTF-8 output on a cp1252 console | A script that emits non-ASCII raises `UnicodeEncodeError` mid-write, losing output that was already computed. | A crash on the *print*, not on the work. Set `PYTHONUTF8=1`, or reconfigure `sys.stdout` at the seam. This repo's ASCII-runtime rule exists for the same reason. |
| `gh pr checks` in a non-interactive loop | Blocks waiting for a terminal that is not there. | A poll that never returns. Use `gh api .../check-runs` instead. |
| `REBASE_HEAD` read as "a rebase is in progress" | The ref survives a finished rebase, so the check reports a state that ended. | A rebase nobody started. An active rebase is a `.git/rebase-merge/` or `.git/rebase-apply/` **directory**, not the ref. |
| Shell `cwd` not preserved between calls | A relative command runs somewhere else and *succeeds* there. One certification artefact was written into the wrong repository this way and recovered by a `mv` that should not have been needed. | The command reports success and the artefact is missing. Use absolute paths in anything a fresh context or a background driver will run. |

The last row is why `compaction-survival` requires absolute paths in an anchor's
resume steps: those are, by construction, commands that run in an environment
nobody set up.
