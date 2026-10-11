## Summary

<!-- What does this change do, and why? One to three sentences. -->

## Related issue

<!-- e.g. "Closes #12". Delete this section if there's no related issue. -->

## Type of change

- [ ] Skill / plugin content (`SKILL.md`, references, scripts)
- [ ] Hook behavior
- [ ] Eval harness or datasets
- [ ] Docs only
- [ ] Tooling / CI / repo config

## Checklist

- [ ] `uvx pre-commit==4.6.2 run --all-files` passes (ruff lint + format, hygiene, railform hooks, register linter, structural validator)
- [ ] `uv run --no-project --with pyyaml -- python scripts/run_tests.py` passes
- [ ] New or changed scripts ship a `test_<name>.py` beside them
- [ ] README / docs updated if commands or behavior changed
- [ ] Bumped the affected plugin's `version` in its `plugin.json` (for release-worthy changes)
