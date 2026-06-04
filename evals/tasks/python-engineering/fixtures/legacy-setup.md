# Existing Python project setup (to review)

Layout (flat, no `src/`):

```
myapp/__init__.py
myapp/main.py
myapp/utils.py
tests/test_main.py
requirements.txt
setup.py
```

- No `pyproject.toml`. Dependencies live in `requirements.txt`, installed with
  `pip` into a hand-made `virtualenv`. `setup.py` uses `setuptools`.
- The README says "run `poetry install`" — the repo half-migrated to poetry and
  stalled, so both pip and poetry instructions exist.
- No linter or formatter config. No type checker. No pre-commit. No CI.
- Tests run with `python -m unittest`.
- Configuration is read ad hoc with `os.environ.get(...)` scattered across modules;
  missing env vars surface as `None` deep in the call stack at runtime.
