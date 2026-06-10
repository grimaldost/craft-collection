# Defense in Depth

Fixing a bug caused by invalid data with one validation check feels
sufficient — until a different code path, a refactor, or a mock bypasses that
single check. Validate at every layer the data passes through. One check
fixes the bug; layered checks make it structurally impossible.

## The four layers

**1. Entry-point validation** — reject obviously invalid input at the API
boundary:

```typescript
function createProject(name: string, workingDirectory: string) {
  if (!workingDirectory || workingDirectory.trim() === '') {
    throw new Error('workingDirectory cannot be empty');
  }
  if (!existsSync(workingDirectory)) {
    throw new Error(`workingDirectory does not exist: ${workingDirectory}`);
  }
  // ... proceed
}
```

**2. Business-logic validation** — confirm the data makes sense for this
specific operation, even if the entry point should have caught it:

```typescript
function initializeWorkspace(projectDir: string, sessionId: string) {
  if (!projectDir) throw new Error('projectDir required for workspace initialization');
  // ... proceed
}
```

**3. Environment guards** — refuse dangerous operations in contexts where
they cannot be legitimate:

```typescript
async function gitInit(directory: string) {
  if (process.env.NODE_ENV === 'test') {
    const normalized = normalize(resolve(directory));
    if (!normalized.startsWith(normalize(resolve(tmpdir())))) {
      throw new Error(`Refusing git init outside temp dir during tests: ${directory}`);
    }
  }
  // ... proceed
}
```

**4. Debug instrumentation** — capture context (inputs, cwd, stack) before
the operation, for forensics when the other layers miss.

## Applying the pattern

1. Trace the data flow: where does the bad value originate, where is it used.
2. Map every checkpoint the value passes through.
3. Add validation at each layer — entry, business, environment, debug.
4. Test each layer by bypassing the previous one and confirming the next
   catches it.

## Why all the layers earn their keep

In the originating case (an empty `projectDir` reaching `git init` from a
test), each layer caught failures the others missed once added: alternate
code paths bypassed the entry validation, mocks bypassed the business-logic
checks, and platform edge cases needed the environment guard. The debug layer
identified the structural misuse that motivated the fix at the source.
