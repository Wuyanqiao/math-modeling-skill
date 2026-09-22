# Contributing

Develop from the user-owned fork and retain `upstream` for the source project. Record the upstream commit when synchronizing; keep functional changes separate from generated bundles. Existing source attribution and notices must remain intact.

Use Python 3.11–3.13. Create a virtual environment and run `python -m pip install -r requirements-dev.txt`. The core runtime uses the standard library; optional document, figure and spreadsheet dependencies are declared in `pyproject.toml`. Installation and capability details are in [the installation guide](docs/installation.md).

Before submitting a change:

1. Run `python -m unittest discover -s tests -v` and relevant external-tool checks. Report skipped checks and missing binaries explicitly.
2. For adapter changes, run `node --test tests/dsh/*.test.mjs` with Node 22 or 24. These tests do not prove mounting in an installed DSH host; report any host smoke test separately.
3. Run `python tools/docx/scripts/self_check.py` when changing the compatibility DOCX tools.
4. After all source edits, run `python scripts/sync_dsh_plugin.py --apply`, then `python scripts/sync_dsh_plugin.py --check`. Edit the canonical source tree; the DSH knowledge/tool directory is generated.
5. Run `python scripts/build_distribution.py --mode local-development`. The builder checks required resources, executable Python syntax, local resource links, file hashes, project initialization, persisted state and incomplete-project detection in a temporary Chinese path containing spaces.

Add regression tests for state transitions, artifact integrity, output validation and compatibility boundaries. Tests should verify observable behavior. Use deterministic data and record random seeds. Keep credentials, user contest data, generated papers, virtual environments and build archives out of Git.

A useful change description names the concrete before/after behavior, explains compatibility effects and records the commands actually run. For externally reported problems, distinguish fixed behavior from remaining reproduction gaps.

Release changes must update `VERSION` and the changelog. A state or receipt compatibility change requires a major version and a migration explanation. Skill and adapter bundles are generated from the same source snapshot and contain a file manifest; no manual knowledge-only copy is a complete distribution.

The default release build currently fails because source authorization has not been established. Do not bypass this by deleting licenses or marking unknown components allowed. Document verified permission or replace a component with an independently implemented, explicitly licensed alternative, update `THIRD_PARTY_NOTICES.md` and the distribution policy, then run the release check. Local validation archives are not publishable artifacts.
