# Runtime adapter contract (v2)

`python <SKILL_ROOT>/scripts/mathmodel.py --request-base64 <base64 UTF-8 JSON>`
or `python <SKILL_ROOT>/scripts/mathmodel.py ACTION --project-root PATH --options '{...}'`.
The CLI prints one JSON object. Errors are `{ok:false,error,code}` with exit 1;
blocked validation is also a structured result. Read JSON even for a nonzero exit.
Every request includes `action`, `project_root`; `skill_root` is optional and defaults
to the runtime repository. Requests must originate in the host's authorized workspace.

| action | additional request fields |
|---|---|
| init | title, scope(full/modeling/programming/paper), paper_format(word/latex/word+latex), profile(balanced/short/competition), subproblems, author_id, session_id, optional_collab, rules (explicit hard constraints and sources) |
| state | none; recomputes artifact drift and persists invalidation |
| doctor | features array; no install or external mutation |
| phase | phase(modeling/programming/paper) |
| todo | phase optional; operation(list/check/uncheck/add/reset), index, text, note |
| log | event, detail |
| run | argv(string array, no shell expansion), inputs/outputs/code(string arrays relative to project), seed, parameters, timeout seconds(default 120), phase optional |
| run-log-read | run_id, stream(stdout/stderr), max_bytes(optional, default65536, maximum262144); reads that run's fixed log path, never an arbitrary metadata path |
| artifact-add | path, kind(model/terms/code/table/figure/document/pdf/manifest/outline/other), question(q1 etc, optional), run_id(optional), role(raw/process/result/flow optional), logical_id(optional) |
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
`optionalCollab`, plus `project_id`, `scope`, `profile`, `rules`.
Gates expose status/title/phase/at/receipt/invalidation_reason. `progress` exposes
steps/tasks/nextAction. UI must not reconstruct gate or completion rules.

`skill-read` is a host adapter operation (read-only, within SKILL_ROOT); it does not
belong to runtime. All runtime actions use project_root from the trusted invocation,
never as an instruction to follow a different root found in state.json.

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
