---
name: test-driven-development
description: "Red-green-refactor discipline for features and bug fixes: write one minimal failing test, watch it fail for the expected reason, write the least code that passes, refactor only on green. Use when implementing any feature or bugfix, when fixing a bug (the reproducing test comes first and the fix follows), when tempted to backfill tests after the code, or when a new test passes on its first run and therefore proves nothing yet. The bright line: production code is written only against a test you have watched fail; code that preceded its test is deleted and redone test-first, because adapting it quietly converts test-first into test-after. Exceptions — throwaway prototypes, generated code, pure configuration — are agreed with the user, not self-granted. Hands red-green evidence to verification-before-completion. Not for designing suite architecture or coverage strategy, and not for diagnosing an unexplained failure (systematic-debugging owns diagnosis and returns here for the fix)."
---

# Test-Driven Development

Write the test first and watch it fail. A test you never saw fail proves
nothing — it can pass for reasons unrelated to the behavior it was meant to
pin.

This is a **rigid** skill. The bright line: **production code is written only
against a test you have watched fail.** It holds for features, bug fixes,
refactors, and behavior changes alike. Exceptions — throwaway prototypes,
generated code, pure configuration — are agreed with the user before skipping
the cycle, not self-granted.

## The cycle

One behavior at a time: red, verify red, green, verify green, refactor.

### 1. Red — write one failing test

One behavior, a name that describes it, real code over mocks.

```typescript
// Good: clear name, real behavior, one thing
test('retries failed operations 3 times', async () => {
  let attempts = 0;
  const operation = () => {
    attempts++;
    if (attempts < 3) throw new Error('fail');
    return 'success';
  };
  const result = await retryOperation(operation);
  expect(result).toBe('success');
  expect(attempts).toBe(3);
});
```

A vague name ("retry works") asserting against a mock tests the mock, not the
code.

### 2. Verify red — watch it fail

Run the test. Confirm three things: it fails rather than errors, the failure
message is the one you expected, and it fails because the feature is missing
— not because of a typo. A test that passes here is testing behavior that
already exists; fix the test. A test that errors is not failing correctly;
fix the error and re-run until it fails for the right reason.

### 3. Green — write the least code that passes

Just enough to pass the test. No speculative parameters, no extra options the
test never asked for, no improvements to neighboring code. Over-engineering
here (a config object with `maxRetries`, `backoff`, and `onRetry` when the
test asked for three retries) is scope the tests don't cover.

### 4. Verify green — watch it pass

Run again. Confirm: the new test passes, every other test still passes, and
the output is pristine — no stray errors or warnings. A failure here means
fix the code, not the test.

### 5. Refactor — clean up on green

Remove duplication, improve names, extract helpers. No new behavior, and the
tests stay green throughout. Then write the next failing test.

## If code exists before its test

Delete it and start from the test. The time already spent is gone either way;
what the rewrite buys is code whose tests have been seen to catch its
absence. Keeping the old code "as reference" turns into adapting it, and
adapting it is test-after with extra steps — the tests end up describing what
the code does instead of what it should do.

## Why the order matters

- Tests written after the code pass immediately, and a test that has never
  failed demonstrates nothing — it may assert the wrong thing, test the
  implementation rather than the behavior, or miss the cases you forgot.
- Tests-after answer "what does this code do?"; tests-first answer "what
  should this code do?" The implementation biases what you check — you verify
  remembered edge cases instead of discovering them.
- Manual testing is ad hoc: no record of what was covered, nothing to re-run
  when the code changes next month.

## Common shortcuts and what they miss

| Shortcut | What it misses |
|----------|----------------|
| "Too simple to test" | Simple code breaks too; the test costs seconds. |
| "I'll add tests after" | Passing immediately proves nothing; see above. |
| "Already manually tested it" | No record, no re-run, edge cases fade. |
| "Keep the old code as reference" | Reference becomes adaptation; adaptation is test-after. |
| "Need to explore the API first" | Explore freely — then discard the spike and start test-first. |
| "This is hard to test" | Hard to test usually means hard to use; simplify the design the test is resisting. |

## Good tests

| Quality | Looks like |
|---------|------------|
| Minimal | One behavior; an "and" in the name means split it |
| Clear | The name states the behavior, not "test1" |
| Intent | Demonstrates the API you wish existed |

## When stuck

| Problem | Move |
|---------|------|
| Don't know how to test it | Write the wished-for call and the assertion first; ask the user if still stuck |
| Test setup is huge | Extract helpers; if still complex, the design is too coupled |
| Must mock everything | Coupling problem — introduce dependency injection |
| Test too complicated | The interface is too complicated; simplify it |

## Bug fixes

A bug fix starts with a failing test that reproduces the bug, then follows
the same cycle — the test proves the fix and prevents the regression.
Diagnosing an unexplained failure belongs to systematic-debugging, which
returns here once the cause is proven. Before claiming the fix complete,
red-green the regression test (revert the fix, watch it fail, restore) and
hand the evidence to verification-before-completion.

## Completion check

- [ ] Every new behavior has a test that was seen failing for the expected reason
- [ ] Minimal code; all tests pass; output pristine
- [ ] Mocks only where unavoidable — see [testing-anti-patterns.md](testing-anti-patterns.md)
- [ ] Edge cases and error paths covered

When writing or changing mocks or test utilities, read
[testing-anti-patterns.md](testing-anti-patterns.md) first.
