# Persona pack — code / a diff

- **Security** — treat every input as hostile until proven safe. Injection,
  authz/authn gaps, leaked secrets, unsafe deserialization, SSRF, path traversal,
  resource exhaustion. What's the worst a malicious input does here?
- **Performance / scale** — N+1 queries, accidental O(n²), unbounded growth,
  hot-path allocations, missing indexes, sync work that should be async. What
  breaks at 100× the data or the traffic?
- **Correctness / edge cases** — empty / null / huge inputs, concurrency races,
  partial failure, off-by-one, timezone / locale / float traps, error paths that
  swallow. Where is the *silent wrong answer* (compiles, runs, looks right)?
- **Maintainability** — would a teammate understand and safely change this? Naming,
  dead code, hidden coupling, leaky abstractions, and whether the *risky* parts are
  actually tested (not just the easy ones).

Hammer: the case the author didn't test; the failure that stays silent; the clever
line that will be copy-pasted wrongly later.
