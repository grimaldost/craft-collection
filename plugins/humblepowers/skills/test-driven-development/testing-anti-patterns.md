# Testing Anti-Patterns

Read this when writing or changing tests, adding mocks, or tempted to add a
test-only method to production code.

Mocks isolate; they are not the thing under test. Three bright lines: test
real behavior, not mock behavior; no test-only methods in production classes;
no mocking without understanding the dependency chain.

## 1. Testing mock behavior

```typescript
// Bad: verifies the mock exists, not that the component works
test('renders sidebar', () => {
  render(<Page />);
  expect(screen.getByTestId('sidebar-mock')).toBeInTheDocument();
});

// Good: test the real component, or don't assert on the mock at all
test('renders sidebar', () => {
  render(<Page />);
  expect(screen.getByRole('navigation')).toBeInTheDocument();
});
```

The check before asserting on any mocked element: is this real component
behavior, or just mock existence? If the assertion disappears when the mock
does, it was testing the mock.

## 2. Test-only methods in production classes

A `destroy()` that only tests call pollutes the production API, invites
accidental production use, and confuses object lifecycle with entity
lifecycle. Cleanup that exists for tests belongs in test utilities:

```typescript
// test-utils/ — production Session stays stateless
export async function cleanupSession(session: Session) {
  const workspace = session.getWorkspaceInfo();
  if (workspace) await workspaceManager.destroyWorkspace(workspace.id);
}
```

Two questions before adding any method to a production class: is it only used
by tests (move it to test utilities), and does this class own the resource's
lifecycle (if not, it is the wrong home regardless).

## 3. Mocking without understanding the dependency chain

```typescript
// Bad: the mocked method had a side effect the test depends on
vi.mock('ToolCatalog', () => ({
  discoverAndCacheTools: vi.fn().mockResolvedValue(undefined), // skips config write!
}));
await addServer(config);
await addServer(config); // should throw on duplicate — never does

// Good: mock the genuinely slow/external part, preserve the behavior the test needs
vi.mock('MCPServerManager');
```

Before mocking a method, list its side effects and check whether the test
depends on any of them. When unsure, run the test against the real
implementation first and observe what actually has to happen — then mock
minimally, at the level of the slow or external operation. "Mocking it to be
safe" is how tests pass for the wrong reason.

## 4. Incomplete mocks

A mock that includes only the fields the immediate test touches hides
structural assumptions: downstream code reads the fields you omitted, the
test passes, integration fails. Mirror the complete real structure —
everything the real API returns — and verify the mock against the documented
schema. When uncertain, include every documented field.

## 5. Tests as an afterthought

"Implementation complete, ready for testing" inverts the cycle — testing is
part of implementation, not a follow-up phase. The TDD cycle (failing test,
minimal code, refactor) is what makes this anti-pattern structurally
impossible.

## When mocks grow too complex

Warning signs: mock setup longer than the test logic, mocks missing methods
the real component has, tests that break when the mock changes rather than
when behavior changes, no crisp answer to "why is this mocked?" An
integration test against real components is often simpler and stronger than a
tower of mocks.

## Why TDD prevents these

Writing the test first forces you to decide what real behavior is being
pinned; watching it fail confirms the test exercises real code rather than
mock wiring; minimal implementation keeps test-only methods from creeping in;
and meeting the real dependencies before mocking shows what the test actually
needs. Asserting on mock behavior is a sign the cycle was skipped — the test
never failed against real code.

## Quick reference

| Anti-pattern | Fix |
|--------------|-----|
| Asserting on mock elements | Test the real component, or stop mocking it |
| Test-only methods in production | Move to test utilities |
| Mocking without understanding | Map side effects first; mock at the lowest slow/external level |
| Incomplete mocks | Mirror the real structure completely |
| Tests as afterthought | The cycle: failing test first |
| Over-complex mocks | Prefer an integration test |
