# Condition-Based Waiting

Flaky tests often guess at timing with arbitrary delays — they pass on a fast
machine and fail under load or in CI. Wait for the condition you actually
care about, not a guess about how long it takes.

Use this when tests carry arbitrary sleeps, flake intermittently, or time out
when parallelized. The exception is a test of genuine timing behavior
(debounce or throttle intervals), where a delay is the subject — document why.

## The core pattern

```typescript
// Before: guessing at timing
await new Promise(r => setTimeout(r, 50));
expect(getResult()).toBeDefined();

// After: waiting for the condition
await waitFor(() => getResult() !== undefined, 'result available');
expect(getResult()).toBeDefined();
```

## Quick patterns

| Waiting for | Pattern |
|-------------|---------|
| An event | `waitFor(() => events.find(e => e.type === 'DONE'), 'done event')` |
| A state | `waitFor(() => machine.state === 'ready', 'machine ready')` |
| A count | `waitFor(() => items.length >= 5, 'five items')` |
| A file | `waitFor(() => fs.existsSync(path), 'output file')` |

## Implementation

```typescript
async function waitFor<T>(
  condition: () => T | undefined | null | false,
  description: string,
  timeoutMs = 5000
): Promise<T> {
  const startTime = Date.now();
  while (true) {
    const result = condition();
    if (result) return result;
    if (Date.now() - startTime > timeoutMs) {
      throw new Error(`Timeout waiting for ${description} after ${timeoutMs}ms`);
    }
    await new Promise(r => setTimeout(r, 10));
  }
}
```

## Common mistakes

- **Polling every millisecond** wastes CPU; ~10ms is plenty.
- **No timeout** loops forever when the condition never holds — always bound
  it, with a description in the error.
- **Reading stale state** — call the getter inside the loop, not before it.

## When an arbitrary delay is justified

After the triggering condition has been awaited, when the wait is derived
from a known interval rather than a guess, and with a comment stating the
derivation:

```typescript
await waitForEvent(manager, 'TOOL_STARTED'); // condition first
await new Promise(r => setTimeout(r, 200)); // then 2 ticks at the tool's 100ms interval
```
