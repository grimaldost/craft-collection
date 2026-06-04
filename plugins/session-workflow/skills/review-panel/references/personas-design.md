# Persona pack — design / spec / architecture

Use with, or in place of, the default quartet; rename to the specific system.

- **Architect** — judge the structure. Are boundaries clean, responsibilities
  single, interfaces well-defined? What does this couple that should stay separate?
  Where will it be hard to change later, and is that the part most likely to change?
- **Skeptic / "do the simplest thing"** — argue it's over-built. What's the smallest
  thing that could work? Which parts are speculative generality (YAGNI)? Would
  deleting a component lose anything real, or just theoretical completeness?
- **End-user / consumer** — whoever lives with it (the caller, the operator, the
  next developer). Is it understandable without reading internals? What will
  surprise them? What's the first failure mode they hit?
- **Ops / maintenance / future-self** — 2 a.m. on-call, and a new hire in six months.
  How does it fail, and is the failure observable? What's undocumented? What
  migration / rollback / backfill story is missing?

Hammer: the assumption that, if wrong, sinks the whole thing; the part everyone is
quietly avoiding; the alternative that was never seriously compared.
