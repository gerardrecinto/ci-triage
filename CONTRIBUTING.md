# Contributing

Bug reports and small pull requests are welcome.

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

- Add a fixture log under `tests/fixtures/` and a test for any new rule or parser change.
- Keep the core dependency-free. The LLM client is an optional extra.
- Update `CHANGELOG.md` and keep `pyproject.toml` and `src/ci_triage/__init__.py` on the same version (a test checks this).
- One change per pull request.
