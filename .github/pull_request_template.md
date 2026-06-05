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

- [ ] `uv tool run pre-commit run --all-files` passes (ruff lint + format, JSON/YAML, structural validator)
- [ ] `python scripts/run_tests.py` passes
- [ ] New or changed scripts ship a `test_<name>.py` beside them
- [ ] README / docs updated if commands or behavior changed
- [ ] Bumped the affected plugin's `version` in its `plugin.json` (for release-worthy changes)
