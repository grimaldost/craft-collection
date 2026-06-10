# Root Cause Tracing

Bugs often surface deep in the call stack — a `git init` in the wrong
directory, a file created in the wrong place, a database opened with the
wrong path. The instinct is to patch where the error appears; that treats the
symptom. Trace backward through the call chain to the original trigger and
fix at the source.

Use this when the error happens deep in execution, the stack trace shows a
long chain, or it's unclear where an invalid value originated.

## The tracing process

1. **Observe the symptom.** `git init failed in ~/project/packages/core`.
2. **Find the immediate cause.** What code directly does this?
   `execFileAsync('git', ['init'], { cwd: projectDir })`.
3. **Ask what called it, repeatedly.**
   `WorktreeManager.createSessionWorktree(projectDir, ...)` ←
   `Session.initializeWorkspace()` ← `Session.create()` ← the test.
4. **Inspect the value at each hop.** `projectDir = ''` — and an empty `cwd`
   resolves to `process.cwd()`: the source tree.
5. **Find the original trigger.** The test accessed `context.tempDir` before
   `beforeEach` populated it; the setup helper returns `{ tempDir: '' }`
   initially. That is the source — fix there (e.g., a getter that throws when
   read before setup), not at the `git init` call.

## Adding instrumentation when manual tracing stalls

Capture the stack and context immediately before the dangerous operation:

```typescript
async function gitInit(directory: string) {
  console.error('DEBUG git init:', {
    directory,
    cwd: process.cwd(),
    stack: new Error().stack,
  });
  await execFileAsync('git', ['init'], { cwd: directory });
}
```

In tests, prefer `console.error` over a logger — loggers are often
suppressed. Log before the operation, not after it fails. Include the inputs,
the cwd, and relevant environment. Then run and filter:

```bash
npm test 2>&1 | grep 'DEBUG git init'
```

Read the captured stacks for the test file names and line numbers that
trigger the call, and for the shared pattern across occurrences.

## Finding which test pollutes shared state

When an artifact appears during a test run and the culprit is unknown, bisect:
run the tests one at a time (or in halves) and stop at the first run where
the artifact appears. Automate the loop if the situation recurs.

## The principle

The point where the error appears is the last place to patch. Trace up until
the chain ends — that is the source; fix it there. Then make the bug
structurally unrepeatable by validating at the layers the bad value passed
through on its way down: see [defense-in-depth.md](defense-in-depth.md).
