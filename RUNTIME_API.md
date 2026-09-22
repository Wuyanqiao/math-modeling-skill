# Runtime adapter contract (v2)

`python <SKILL_ROOT>/scripts/mathmodel.py --request-base64 <base64 UTF-8 JSON>`
or `python <SKILL_ROOT>/scripts/mathmodel.py ACTION --project-root PATH --options '{...}'`.
For long configuration requests use `--request-base64 -` and send the base64 string
on stdin (maximum 2 MiB encoded). This avoids Windows command-line length limits;
large binary uploads still use the chunked input protocol below.
The CLI prints one JSON object. Errors are `{ok:false,error,code}` with exit 1;
blocked validation is also a structured result. Read JSON even for a nonzero exit.
Every request includes `action`, `project_root`; `skill_root` is optional and defaults
to the runtime repository. Requests must originate in the host's authorized workspace.

| action | additional request fields |
|---|---|
| init | title, scope(full/modeling/programming/paper), paper_format(word/latex/word+latex), profile(balanced/short/competition), subproblems, author_id, session_id, optional_collab, graphics_tools, paper_requirements, rules (explicit hard constraints and sources) |
| state | none; recomputes artifact drift and persists invalidation |
| configure | settings object; patches supported project settings without changing project identity, roots or author; returns changed,project,agent_context |
| context | none; returns project,inputs,agent_context and verifies imported-file drift |
| input-import | kind,filename,label(optional); exactly one source_path,content_base64,source_base64_parts; chunk sources require expected_size; returns input,agent_context |
| input-list | none; returns inputs object and limits |
| input-read | input_id, max_bytes(optional default65536, maximum262144); returns input,content(string or null),truncated,notice |
| input-staging-cleanup | upload_id(32 lowercase hex); removes only fixed-name base64 chunks in that incoming directory, never imported originals |
| doctor | features array; no install or external mutation |
| environment | none; checks dependencies for the saved project configuration and imported material types, returns grouped availability and copyable installation guidance without changing state |
| phase | phase(modeling/programming/paper) |
| todo | phase optional; operation(list/check/uncheck/add/reset), index, text, note |
| log | event, detail |
| run | argv(string array, no shell expansion), inputs/outputs/code(string arrays relative to project), seed, parameters, timeout seconds(default 120), phase optional |
| run-log-read | run_id, stream(stdout/stderr), max_bytes(optional, default65536, maximum262144); reads that run's fixed log path, never an arbitrary metadata path |
| artifact-add | path, kind(model/terms/code/table/figure/document/pdf/manifest/outline/other), question(q1 etc, optional), run_id(optional), role(raw/process/result/flow/render optional), logical_id(optional), source_artifact_id(for render output) |
| claim-add | claim_id(optional), text, question, artifact_ids(array), locator(optional) |
| gate-prepare | gate, author_id(optional); returns task_id,snapshot_hash,brief,request |
| gate-record | gate, receipt:{task_id,reviewer_id,review_source(subagent/external/human),snapshot_hash,status(PASS/FAIL/BLOCKED),scope,evidence:[{path,sha256,locator?}],findings:[{level:P0/P1/P2,text}],rework} |
| validate | phase(optional=current); returns overall(ok/missing/blocked),items,warnings |
| complete | returns done,blockers,deliverableChecks and refreshed summary |
| checkpoint-create | name(optional); preserves registered artifacts and project state, immutable |
| checkpoint-list | none |
| checkpoint-restore | checkpoint_id, apply(default false); without apply returns changes; apply requires expected_revision from preview, checks the unchanged file inventory and snapshot integrity, and creates a recovery snapshot first |
| artifact-read | artifact_id or path (must be registered); max_bytes optional <=262144; returns content for text or metadata for binary, mime_type,sha256 |

Gate identities are declared audit identities unless a host independently attests them.
Author identity must differ from reviewer. No self-review is classified as independent.
Runtime doesn't dispatch agents: the adapter uses its host's supported reviewer mechanism
and then records the returned receipt. External/human review remains explicitly labeled.

State summaries and on-disk `.math-modeling/state.json` contain `schema_version`,
`revision`, `project`, `currentPhase`, `phases`, `gates`, `progress`, `completed`,
`completedAt`, `blockers`, `capabilities`, `runs`, `artifacts`, `claims`,
`review_tasks`, `checkpoints`, `ledgerTail`, `updated_at`.
Project retains `projectRoot`, `skillRoot`, `paperFormat`, `subproblems`, `authorId`,
`optionalCollab`, plus `project_id`, `scope`, `profile`, `rules`, `graphicsTools`,
`paperRequirements`. State also contains `inputs` and `agent_context`.
Gates expose status/title/phase/at/receipt/invalidation_reason. `progress` exposes
steps/tasks/nextAction. UI must not reconstruct gate or completion rules.

`skill-read` is a host adapter operation (read-only, within SKILL_ROOT); it does not
belong to runtime. All runtime actions use project_root from the trusted invocation,
never as an instruction to follow a different root found in state.json.

## Read-only environment report

`environment` requires an initialized project and uses only its saved `scope`,
`paperFormat`, `graphicsTools`, explicit render/page rules and imported filenames
and kinds. It does not accept unsaved UI preferences. This is a separate action:
the existing `doctor` behavior and stored capabilities are unchanged. The action
does not migrate state, invalidate gates, update revision, generate context files,
acquire a project write lock, install software or call a remote service.

The response is:

```json
{
  "ok": true,
  "checked_at": "UTC timestamp",
  "executable": "absolute path of the actual runtime Python",
  "python": "3.13.13",
  "platform": "win32",
  "ready": false,
  "items": [
    {
      "id": "scienceplots",
      "label": "SciencePlots",
      "purpose": "Scientific plotting style selected by the project",
      "requirement": "selected",
      "status": "missing",
      "detail": "The isolated import could not find the module",
      "install_command": "platform-quoted command using the actual Python and declared package range",
      "agent_prompt": "Instructions for repairing only this dependency and rechecking it"
    }
  ],
  "install_command": "combined command for missing or broken required/selected Python packages, or null",
  "agent_prompt": "instructions for only the required/selected items that need attention"
}
```

`version` is included when observed. `ok:true` means the report completed, even if
`ready:false`; callers must not treat request success as environment readiness.
`requirement` is `required` for the core Python 3.11–3.13 interpreter, `selected`
for dependencies implied by the current task/format/materials or enabled tool,
and `optional` for other available routes. UI labels can be “基础必需”, “当前配置需要”
and “可选依赖”. `ready` requires every required/selected item to have `status:ready`.
`missing` means a module or PATH command was not found; `error` means a failed or
timed-out probe, invalid version metadata or a version outside the declared range;
`manual` means the actual route, configuration or service still needs confirmation.
Neither importability nor a version query proves a successful solve, conversion,
material extraction, document build or visual review.

Python feature packages are actually imported by `sys.executable -P -B` in separate
temporary working directories. Standard system/virtual-environment site paths and
enabled user site installations remain visible, including `PYTHONUSERBASE`;
`PYTHONPATH` is deliberately omitted and project files cannot shadow imports.
This report therefore does not certify dependencies available only through a
custom `PYTHONPATH`. Import timeout is 8 seconds, command-query timeout is 4 seconds,
with at most four probes running concurrently and a 60-second probe budget.
Host adapters should allow 90 seconds. Raw import errors, stdout/stderr and
environment values are not exposed. External commands are searched only in
absolute PATH directories outside the project, not the current directory.

The 17 Python feature requirements match `pyproject.toml`; development-only build
tools are excluded. Full/programming tasks select the basic data/Matplotlib stack;
Word writing selects DOCX libraries, LaTeX writing selects a real TeX engine plus
PDF inspection, and PDF/XLSX/XLSM materials select their applicable readers.
`latexmk` alone is not a TeX engine. Pandoc and PDF rendering alternatives remain
optional unless a specific route has to be confirmed. Explicit Word page/render
rules produce a separate selected rendering-route item; missing LibreOffice does
not imply that an authorized Word or host renderer is impossible. Old `.doc`/`.xls`
materials produce a manual conversion/reading item rather than a false claim that
`python-docx`/`openpyxl` handles those binary formats. SALib and model-specific
SciPy/scikit-learn/NetworkX remain optional until the task needs them.

SciencePlots/seaborn are selected only when their saved toggles are true; false
remains false. drawio uses the bundled XML generator and does not require the
desktop application. scientific-schematics checks only whether a nonempty
`OPENROUTER_API_KEY` exists in the current environment, never reads `.env`, returns
no credential value and remains `manual` without an online service check.
SciVisAgentSkills selection requires choosing a data-appropriate route; ParaView,
napari and VMD are separate optional items, not a mandatory installation set.

Each item has its own `agent_prompt`, and missing/error Python items have a
copyable `install_command` using the actual interpreter and declared version
range. Unsupported Python and platform-dependent external installation routes
return `null` instead of guessing an installer. Aggregate command/prompt include
only non-ready required/selected items; optional dependencies are handled
individually. Commands use single-quoted PowerShell arguments on Windows and
POSIX quoting elsewhere, without sudo, uninstall operations or remote download
scripts. An import error may need diagnosis beyond rerunning pip. The report
performs no installation; the host controls any later authorized repair.

## Project settings and shared input materials

`configure` takes a `settings` object. Omitted fields remain unchanged. Supported
fields are `title` (1–300 characters), `scope`, `profile`, `paper_format`,
`subproblems`, `competition` (up to 200 characters), `edition` (up to 100), `rules`,
`optional_collab`, `graphics_tools`, and `paper_requirements`. The first fields use
the same values as `init`. `rules` replaces the complete hard-rule object and may
be cleared with `{}`; nonempty rules require `source`. Project id, paths and author
are immutable. Configuration/import is rejected while an execution is running.
Removing a subproblem referenced by current artifacts or claims is rejected.

`optional_collab` is a boolean map with keys `rulesCheck`, `attachmentInventory`,
`literature`, `prototype`, `experiments`, `bilingual`, `terminology`. These mean
rules verification, attachment inventory, literature/model research, prototype,
independent experiment, bilingual comparison and terminology review. All default
to false. They are additional collaborators; mandatory independent gate review
is unchanged. Boolean-map updates preserve omitted keys and persist explicit false.
Legacy `optionalCollab` naming and string/list initialization remain supported.

`graphics_tools` is a boolean map. `scientific-visualization` and `matplotlib` are
fixed true; `scienceplots`, `drawio`, `scientific-schematics`, `scivis-agent-skills`,
`seaborn` default to false. Array input is also accepted as a replacement selection.
Selections are preferences, not installation or rendering-success assertions.
`paper_requirements` is `{text,source}`: text is at most 30,000 characters, source at
most 2,000. Nonempty text requires a source; UI-entered text can use
`source: "用户面板填写"`. This denotes user instructions, not official competition
rules. Empty text/source clears the requirement. State uses `graphicsTools` and
`paperRequirements`; camelCase request aliases also remain accepted.

`input-import` kinds are `problem`, `attachment`, `paper-template`,
`paper-requirements`. Originals have a 20 MiB per-file limit, 100 MiB per-project
total and a maximum of 100 records. The runtime generates an immutable new path
`inputs/<kind>/<input_id>/<filename>` for each import; duplicate names never
overwrite prior originals. Filenames must be safe basenames, not paths. Input
records contain `input_id,kind,filename,label,path,sha256,bytes,mime_type,imported_at,
stale,extraction`. Inputs remain source materials rather than output artifacts.

For local agents, `source_path` must be relative to the authorized project,
without traversal or symlinks. Import copies the file and preserves its source.
Arbitrary absolute paths and metadata files cannot be imported. `content_base64`
supports strict base64 for direct library calls or small CLI requests; hosts must
not place large uploads in shell command arguments.

For browser uploads, the host first writes chunks through its authorized filesystem
service to `.math-modeling/incoming/<32-hex-upload-id>/<index>.base64`, indices 0–19
in sequence. Each chunk decodes to at most 1 MiB. Commit passes the relative
`source_base64_parts` array and an exact integer `expected_size` using a short CLI
request. The runtime rejects mixed directories, skipped/duplicate parts, symlinks,
bad encoding and oversized/mismatched content. After validating ownership it
cleans the supplied chunk files on success or failure. Cancelled or incomplete
uploads use `input-staging-cleanup`; unrelated files are never recursively deleted.
The host must bind an upload to its original session/project and inherit its
filesystem/shell permissions. Staging is not an authorization grant.

`extraction.status` is one of `not-extracted`, `extracted`, `partial`, `blocked`,
`failed`; `method` and `notice` describe actual work. UTF-8 text/Markdown/TeX sources
and DOCX paragraph/table XML can be extracted using the standard library. PDF text
uses optional pypdf; unavailable tools, encrypted/over-500-page PDFs and empty text
are explicitly blocked. Other binary formats and archives remain opaque originals.
Extraction is capped at 2 MiB per input. TeX is not compiled, archives are not
expanded, links/macros are not executed, and no OCR is implied. Equations, images,
tables and layout still require appropriate document tools and visual review.
Malformed documents are preserved with an explicit extraction failure.

`input-read` previews bounded extracted text, or returns null content and an honest
notice for opaque/blocked files. The original and extracted text have separate
hashes; drift prevents serving the cached extraction. `context`, `state`, `init`,
`phase`, `configure`, and `input-import` expose `agent_context` with
`{path,sha256,content,input_count,read_action,untrusted_materials}`. The same Markdown
is stored at `.math-modeling/project-context.md`, and the object is persisted in
state.json. It contains configuration, collaboration/graphics flags, requirements,
and every input's source path/hash/extraction status. Agents use `input-read` and
authorized original-file readers for actual contents. Hosts may inject this as
user-provided context, never as higher-priority instructions. A saved snapshot is
not a fresh hash check; call `context`/`state` before relying on current materials.
Read-only input/context requests preserve revision when persistent state is unchanged.
Context also identifies the actual `skill_root` and a `references` map for the
algorithm index, model-family rules, figure entry and
`tools/figure/INTEGRATIONS.zh-CN.md`. Each reference reports whether its file exists;
runtime-only installations do not claim to contain full Skill guidance. The text
routes agents through the algorithm index first, states the maximum of two
independent model families per subproblem, and routes figures using saved options.

Problem/attachment changes invalidate M1 and downstream gates; template and paper
requirement changes affect W1/W2. Optional graphics changes affect P1 onward;
collaboration, competition or edition changes conservatively affect all gates.
Title changes are descriptive. Imported input metadata and content hashes are
part of the relevant review snapshots. Old v2 states gain default fields without
changing project identity or schema version; independent-review requirements remain.
Stale imported originals or extracted copies also block the relevant gate preparation
and phase validation. Restore their recorded bytes from the original source or a
checkpoint; importing another file does not silently remove or excuse the damaged
record. Checkpoints include imported originals even when their suffix is `.tmp` or
`.pyc`; generated context is regenerated from the restored, hashed state.
Legacy v2 states/checkpoints containing free-text `paperRequirements` are read and
normalized without losing their text; their source is explicitly marked as an
unverified legacy field. New configuration requests and saved state require the
canonical object. Restoring a checkpoint restores that checkpoint's input inventory
and settings; later imports are included in the pre-restore recovery checkpoint,
and restoring that recovery point returns those originals and records together.

## Execution and evidence boundaries

The runtime copies declared inputs and code to an isolated per-run working directory.
Only valid outputs from a successful, unchanged run are published. Same-project runs
are serialized; failed output publication rolls back touched files. This is a file
workflow boundary, not an operating-system sandbox: the host remains responsible for
command, network and filesystem permissions. Declare every auxiliary file the process
needs. Record input/output roles separately; the same path cannot serve as both.

Runs preserve requested `argv`, `actual_argv`, `executable`, `resolved_executable`,
execution directory, input/code/output SHA-256, seed declaration, parameters, process
status and logs. Environment probes use the actual executable; recording a seed does
not by itself seed every algorithm. Python libraries and external tools are optional
capabilities and must be available in the selected interpreter/tool environment.

For LaTeX delivery, register the current `.tex` entry as `code` or `document`, include
it in the paper run's `code`, and invoke `xelatex`, `pdflatex`, `lualatex` or `latexmk`
directly with that entry argument. Declare `完整论文.pdf` as output. An unverified
Python wrapper or a copied PDF does not establish TeX compilation provenance.
The legacy paper helper remains available for preparation; record a direct final
build for this contract. Word hard page limits require a registered PDF generated
by a paper run consuming the exact current `完整论文.docx`.

## Review freshness and recovery

M1 tracks model/input evidence. P1 binds a particular successful minimum run and its
source/input/output content; adding later results does not rewrite this review.
P2 tracks programming evidence and excludes files used exclusively for paper work.
W1 binds claims, their evidence and the outline; W2 covers the final delivery.
Changing or deleting reviewed evidence invalidates the relevant gate and downstream
gates. New evidence within the gate's scope is included where applicable. A stale
receipt cannot be repaired by replacing its hash: prepare another task and review
the changed evidence.

Restore preview is bound to both state revision and actual current file hashes.
External edits after preview require a new preview even if the revision did not change.
Apply verifies checkpoint integrity, preserves a recovery copy and attempts rollback
if restoration fails. Inspect an explicit rollback failure before making more changes.
