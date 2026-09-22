# Installation and verification

This is a local modeling workbench with a Python runtime, an agent Skill, and an optional DeepSeek Harness adapter. The standard-library runtime can initialize and track work without installing document or scientific packages. Capability checks determine which output validators and converters can actually run.

| Layer | Declared support | Validation scope |
| --- | --- | --- |
| Python core | CPython 3.11, 3.12, 3.13 | Windows/Linux CI uses 3.11 and 3.13; a configured matrix is not a claim of an already completed remote CI run |
| DSH JavaScript adapter | Node 22 and 24 adapter test targets; local host verification uses Node 24.11.1 | Host baseline `@deepseek-ai/dsh@0.1.7-alpha.1`; the official minimum Node version is not asserted |
| Native Word handling | Optional `docx` dependency group | `python-docx`, `lxml`, `defusedxml`, Pillow |
| Figures | Optional `figure` group | NumPy, pandas, Matplotlib, Pillow |
| PDF inspection | Optional `pdf` group | pypdf, PyMuPDF |
| Spreadsheets | Optional `xlsx` group | openpyxl; recalculation may additionally need LibreOffice |
| TeX/Pandoc/rendering | External system tools | Checked by executable probes; installing Python extras does not install these programs |

From a checkout, create and activate a virtual environment. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/mathmodel.py --help
```

On Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/mathmodel.py --help
```

Install only the optional capabilities you need, for example `python -m pip install -e ".[docx,figure,pdf,validation]"`. Contributors can install all test dependencies with `python -m pip install -r requirements-dev.txt`. `requirements-lock-py313.txt` is a direct-dependency constraint snapshot from the Python 3.13 validation environment; it is not a complete transitive lock and should not be used with Python 3.11. To replay that snapshot, add `-c requirements-lock-py313.txt` to the development install command. Other supported Python versions use the compatible ranges declared in `pyproject.toml`.

The runtime wheel contains `mathmodel_runtime` and its schema/profile JSON resources. The `mathmodel` console command invokes the runtime. A wheel is not the full Skill/DSH bundle: compatibility scripts, templates and the reference library are included by the distribution builder described below.

For the inherited Word tools, run:

```bash
python tools/docx/scripts/check_env.py --json
python tools/docx/scripts/check_env.py --json --need-pandoc
python tools/docx/scripts/self_check.py
```

The doctor imports each required module, so an installed but broken extension is reported as unavailable. `defusedxml` is required for the inherited comment/Office path. Pandoc is optional for native DOCX operations and becomes mandatory with `--need-pandoc`; the check runs `pandoc --version`, rather than trusting a filename on PATH. The doctor does not install packages or alter the machine.

Build complete local bundles with:

```bash
python scripts/sync_dsh_plugin.py --apply
python scripts/sync_dsh_plugin.py --check
python scripts/build_distribution.py --mode local-development --output dist
```

The builder reads canonical source files, ignores the checked-in DSH mirror, and constructs a full Skill plus a DSH preset with the same Skill embedded. Executable tools, templates, algorithm references and runtime resources are copied together. It excludes `.git`, virtual environments, `project-review`, caches, logs, runtime state and previous archives. It records source commit, dirty-worktree status, content hash, component versions, dependencies and per-file hashes in manifests. Both copies initialize a project, reload its state and confirm that a project with no deliverables is incomplete, using a fresh temporary directory with Chinese characters and spaces. This smoke test does not establish the correctness of a complete modeling run or an external DSH host installation. CI additionally installs the runtime wheel without optional packages into a fresh virtual environment and repeats these checks outside the checkout with Python isolated mode enabled.

Existing documentation links that already pointed to absent source files are listed in the resource audit. A source resource that exists but is omitted from the bundle fails the build. Required resources and Python syntax failures also fail the build. Missing external converters remain separately reported capabilities.

Local archive filenames include `LOCAL-DEVELOPMENT` and contain a notice stating that they are not approved for redistribution. The release command is `python scripts/build_distribution.py --mode release`; it currently fails explicitly because authorization for inherited and new code has not been established. Restricted DOCX/XLSX/PDF components are excluded from release selection, and unknown components fail closed. See [component provenance](../THIRD_PARTY_NOTICES.md). No archive is uploaded by these commands or CI.

The current host baseline is [`@deepseek-ai/dsh@0.1.7-alpha.1`](https://www.npmjs.com/package/@deepseek-ai/dsh/v/0.1.7-alpha.1), with API source audited at [commit c36a83ff6bb95e3f82cf79f9be7c724270a8aa61](https://github.com/deepseek-ai/deepseek-harness/tree/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61). This host registers presets through the `@deepseek-ai/dsh-agent-preset` service; it does not discover arbitrary `.agent-presets` folders. In the extracted DSH archive, the `math-modeling-agent/plugins/dsh-math-modeling-ui` directory is the self-contained host bundle: it includes the workflow adapter, UI, registration patch and a complete `skills/math-modeling` tree. Install this local bundle through the compatible host's profile/bundle installation mechanism, following the bundled DSH README. The outer legacy preset layout is retained for older installations. Do not copy only the UI JavaScript or assume that placing the outer directory in `.agent-presets` registers it in the current host. An adapter test suite passing does not establish host mounting compatibility.
