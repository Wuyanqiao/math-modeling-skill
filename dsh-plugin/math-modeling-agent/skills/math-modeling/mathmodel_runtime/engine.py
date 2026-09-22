"""Single source of workflow transitions for CLI and host adapters."""

import base64
from copy import deepcopy
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import uuid

from .storage import GATES, PHASES, Store, WorkflowError, atomic_json, digest, inside, now, object_hash, snapshot
from .validation import doctor, fresh_run, inspect_file, phase_validation


RESOURCE_ROOT = Path(__file__).parent / "resources"
TITLES = {"M1": "建模终检", "P1": "最小可运行结果", "P2": "编程终检", "W1": "证据大纲", "W2": "论文终检"}
TASKS = {
    "modeling": ["理解问题与附件", "建立假设、模型和验证合同", "完成分析与符号表", "独立建模审查"],
    "programming": ["检查依赖与输入", "运行最小求解并验收", "验证完整结果及证据", "独立编程审查"],
    "paper": ["建立结论与证据映射", "审核证据大纲", "构建并检查论文及渲染", "独立论文审查"],
}
KINDS = {"model", "terms", "code", "table", "figure", "document", "pdf", "manifest", "outline", "other"}


def identifier(prefix):
    return prefix + "_" + uuid.uuid4().hex[:16]


def load_profile(name):
    if name not in {"balanced", "short", "competition"}:
        raise WorkflowError("Unknown profile: " + str(name))
    return json.loads((RESOURCE_ROOT / "profiles" / (name + ".json")).read_text(encoding="utf-8"))


def collab_options(value):
    keys = ("rulesCheck", "attachmentInventory", "literature", "prototype", "experiments", "bilingual", "terminology")
    result = dict.fromkeys(keys, False)
    if isinstance(value, str):
        value = [x for x in re.split(r"[,，\s]+", value) if x]
    if isinstance(value, list):
        value = {k: True for k in value}
    if value is not None:
        if not isinstance(value, dict) or set(value) - result.keys() or any(not isinstance(v, bool) for v in value.values()):
            raise WorkflowError("optional_collab must name supported boolean collaboration choices")
        result.update(value)
    return result


def fresh_state(store, args):
    scope = args.get("scope", "full")
    if scope not in {"full", *PHASES}:
        raise WorkflowError("scope must be full, modeling, programming or paper")
    paper_format = args.get("paper_format", args.get("paperFormat", "word"))
    if paper_format not in {"word", "latex", "word+latex"}:
        raise WorkflowError("paper_format must be word, latex or word+latex")
    questions = args.get("subproblems", ["q1"])
    if isinstance(questions, str):
        questions = re.split(r"[,，\s]+", questions.strip())
    if not isinstance(questions, list) or not questions or any(not isinstance(q, str) or not re.fullmatch(r"q[1-9]\d*", q) for q in questions) or len(questions) != len(set(questions)):
        raise WorkflowError("subproblems must be distinct q1, q2 ... identifiers")
    profile = args.get("profile", "balanced")
    load_profile(profile)
    rules = args.get("rules", {})
    if not isinstance(rules, dict):
        raise WorkflowError("rules must be an object")
    permitted = {"source", "min_figures", "max_pages", "min_content_units", "require_render"}
    if set(rules) - permitted:
        raise WorkflowError("Unsupported hard rule; record scientific constraints in the model contract")
    if rules and (not isinstance(rules.get("source"), str) or not rules["source"].strip()):
        raise WorkflowError("Explicit hard rules require a source (user instruction or official rule URL)")
    for key in ("min_figures", "max_pages", "min_content_units"):
        if key in rules and (isinstance(rules[key], bool) or not isinstance(rules[key], int) or rules[key] < 0):
            raise WorkflowError(key + " must be a nonnegative integer")
    if "require_render" in rules and not isinstance(rules["require_render"], bool):
        raise WorkflowError("require_render must be boolean")
    author = args.get("author_id", "primary")
    if not isinstance(author, str) or not author.strip():
        raise WorkflowError("author_id must be nonempty")
    project = {"project_id": identifier("project"), "title": args.get("title", "数学建模项目"),
               "projectRoot": str(store.root), "skillRoot": str(store.skill), "paperFormat": paper_format,
               "subproblems": questions, "profile": profile, "scope": scope, "authorId": author,
               "rules": rules, "competition": args.get("competition", "generic"), "edition": args.get("edition", ""),
               "session_id": args.get("session_id"), "optionalCollab": collab_options(args.get("optional_collab", args.get("optionalCollab")))}
    phases = {p: {"enteredAt": None, "tasks": [{"text": t, "done": False, "note": ""} for t in TASKS[p]]} for p in PHASES}
    return {"schema_version": 2, "version": 7, "revision": 0, "initializedAt": now(), "project": project,
            "currentPhase": "modeling" if scope == "full" else scope, "phases": phases,
            "gates": {g: {"status": "pending", "phase": p, "title": TITLES[g], "at": None} for g, p in GATES.items()},
            "completed": False, "completedAt": None, "blockers": [], "capabilities": {}, "runs": {},
            "artifacts": {}, "claims": {}, "review_tasks": {}, "checkpoints": [], "ledger": [], "deliverables": None}


def migrate(store, old):
    if old.get("schema_version") == 2:
        for key in ("gates", "phases", "runs", "artifacts", "claims", "review_tasks"):
            if not isinstance(old.get(key), dict):
                raise WorkflowError("Invalid state object: " + key, "state_corrupt")
        if any(g not in old["gates"] for g in GATES) or any(p not in old["phases"] for p in PHASES):
            raise WorkflowError("State is missing phases or gates", "state_corrupt")
        return old
    if old.get("schema_version") is not None or old.get("version", 0) not in range(1, 7):
        raise WorkflowError("Unsupported state version; cannot safely migrate", "state_version")
    backup = store.meta / ("state-v" + str(old.get("version")) + "-" + uuid.uuid4().hex[:8] + ".backup.json")
    atomic_json(backup, old)
    project = old["project"]
    state = fresh_state(store, {"title": project.get("title"), "paper_format": project.get("paperFormat", "word"),
                                "subproblems": project.get("subproblems", ["q1"]), "optional_collab": project.get("optionalCollab")})
    state["currentPhase"] = old.get("currentPhase") if old.get("currentPhase") in PHASES else "modeling"
    for phase in PHASES:
        tasks = old.get("phases", {}).get(phase, {}).get("tasks")
        if isinstance(tasks, list) and all(isinstance(t, dict) and isinstance(t.get("text"), str) for t in tasks):
            state["phases"][phase]["tasks"] = tasks
    state["migration"] = {"from_version": old.get("version"), "backup": backup.name,
                           "notice": "Legacy PASS receipts lack trusted snapshots; review again under v2."}
    return state


def required_gates(state):
    scope = state["project"]["scope"]
    return [g for g, phase in GATES.items() if scope == "full" or scope == phase]


def event(state, name, detail=None):
    state["ledger"].append({"at": now(), "event": name, "detail": detail})
    state["ledger"] = state["ledger"][-500:]


def invalidate(store, state):
    earliest = None
    order = list(GATES)
    for i, gate in enumerate(order):
        node = state["gates"][gate]
        if node["status"] != "pass":
            continue
        current = snapshot(store.root, state, GATES[gate], gate=gate)
        if node.get("snapshot_hash") != current["hash"]:
            earliest = i if earliest is None else min(earliest, i)
    if earliest is not None:
        affected = []
        for gate in order[earliest:]:
            if state["gates"][gate]["status"] == "pass":
                state["gates"][gate].update(status="invalidated", invalidation_reason="Inputs, artifact set, content or project rules changed")
                affected.append(gate)
        state["completed"] = False
        state["completedAt"] = None
        event(state, "gates_invalidated", {"gates": affected})
    for artifact in state["artifacts"].values():
        try:
            path = inside(store.root, artifact["path"])
            artifact["stale"] = not path.is_file() or digest(path) != artifact["sha256"]
        except (WorkflowError, OSError):
            artifact["stale"] = True
    if any(state["gates"][gate]["status"] != "pass" for gate in required_gates(state)) or any(run.get("status") == "running" for run in state["runs"].values()):
        state["completed"], state["completedAt"] = False, None


def projection(state):
    required = required_gates(state)
    tasks = {}
    steps = []
    for phase in PHASES:
        entries = state["phases"][phase]["tasks"]
        done = sum(bool(t.get("done")) for t in entries)
        tasks[phase] = {"done": done, "total": len(entries), "pct": round(100 * done / len(entries)) if entries else 0}
        phase_gates = [g for g in required if GATES[g] == phase]
        status = "not_required" if not phase_gates else "done" if all(state["gates"][g]["status"] == "pass" for g in phase_gates) else "current" if state["currentPhase"] == phase else "pending"
        steps.append({"key": phase, "label": {"modeling": "建模手", "programming": "编程手", "paper": "论文手"}[phase], "status": status})
        for gate in (g for g in GATES if GATES[g] == phase):
            state["phases"][phase]["gate" + gate] = deepcopy(state["gates"][gate])
    unmet = [g for g in required if state["gates"][g]["status"] != "pass"]
    state["required_gates"] = required
    state["progress"] = {"steps": steps, "tasks": tasks, "nextAction": "准备独立审核 " + unmet[0] if unmet else "运行 complete 检查当前交付物"}
    state["ledgerTail"] = state["ledger"][-12:]
    state["initialized"] = True
    return state


def prereqs(state, gate):
    order = required_gates(state)
    if gate not in order:
        raise WorkflowError("Gate does not belong to this task scope")
    missing = [g for g in order[:order.index(gate)] if state["gates"][g]["status"] != "pass"]
    if missing:
        raise WorkflowError("Prerequisite gates are not current PASS: " + ", ".join(missing), "gate_prerequisite")


def claim_check(store, state):
    errors = []
    for question in state["project"]["subproblems"]:
        claims = [c for c in state["claims"].values() if c["question"] == question]
        if not claims:
            errors.append("Missing claim and evidence for " + question)
        for claim in claims:
            for aid in claim["artifact_ids"]:
                artifact = state["artifacts"].get(aid)
                if not artifact or artifact.get("stale"):
                    errors.append("Missing or stale claim artifact " + aid)
                elif not inspect_file(store.root, artifact["path"], artifact["kind"])["ok"]:
                    errors.append("Invalid claim artifact " + aid)
    return errors


def gate_check(store, state, gate, minimal_run_id=None):
    if gate == "P1":
        runs = [r for r in state["runs"].values() if r.get("phase") == "programming"]
        candidate = state["runs"].get(minimal_run_id) if minimal_run_id else (runs[-1] if runs else None)
        return [] if candidate and fresh_run(store.root, candidate) else ["P1 requires a recorded successful execution of current code"]
    if gate == "W1":
        return claim_check(store, state)
    result = phase_validation(store.root, state, GATES[gate], load_profile(state["project"]["profile"]))
    return [i["name"] + ": " + i["note"] for i in result["items"] if not i["ok"]]


def artifact_add(store, state, args):
    path = inside(store.root, args.get("path", ""))
    relative = path.relative_to(store.root).as_posix()
    kind = args.get("kind", "other")
    if kind not in KINDS:
        raise WorkflowError("Unknown artifact kind")
    inspected = inspect_file(store.root, relative, kind)
    if not inspected["ok"]:
        raise WorkflowError("Artifact failed validation: " + "; ".join(inspected["errors"]), "artifact_invalid")
    question = args.get("question")
    if question and question not in state["project"]["subproblems"]:
        raise WorkflowError("Unknown subproblem")
    run_id = args.get("run_id")
    if run_id:
        run = state["runs"].get(run_id)
        if not run or run["exit_code"] != 0 or not any(x["path"] == relative and x["sha256"] == inspected["sha256"] for x in run["outputs"]):
            raise WorkflowError("Run did not produce this artifact version", "provenance_mismatch")
    existing = next((a for a in state["artifacts"].values() if a["path"] == relative), {})
    aid = existing.get("artifact_id", identifier("artifact"))
    entry = {**existing, "artifact_id": aid, "path": relative, "kind": kind, "sha256": inspected["sha256"],
             "bytes": inspected["bytes"], "question": question or existing.get("question"), "run_id": run_id or existing.get("run_id"),
             "validation": inspected, "stale": False, "registered_at": now()}
    for key in ("role", "logical_id", "source_artifact_id"):
        if key in args:
            entry[key] = args[key]
    if entry.get("source_artifact_id") and entry["source_artifact_id"] not in state["artifacts"]:
        raise WorkflowError("Source artifact is not registered")
    if not entry.get("logical_id"):
        stem = re.sub(r"([_-](gray|grey|grayscale|preview))+$", "", path.stem, flags=re.I)
        entry["logical_id"] = str(path.parent.relative_to(store.root) / stem).replace("\\", "/")
    state["artifacts"][aid] = entry
    event(state, "artifact_registered", {"artifact_id": aid, "path": relative})
    return {"ok": True, "artifact": entry}


def execute_action(store, state, action, args):
    if action == "state":
        return {"ok": True, **projection(state)}
    if action == "doctor":
        result = doctor(args.get("features"))
        state["capabilities"] = result["capabilities"]
        return result
    if action == "phase":
        phase = args.get("phase")
        if phase not in PHASES or state["project"]["scope"] not in {"full", phase}:
            raise WorkflowError("Phase is outside this task scope")
        first = next(g for g in required_gates(state) if GATES[g] == phase)
        prereqs(state, first)
        state["currentPhase"] = phase
        state["phases"][phase]["enteredAt"] = state["phases"][phase]["enteredAt"] or now()
        event(state, "phase_enter", {"phase": phase})
        return {"ok": True, "phase": phase}
    if action == "todo":
        phase = args.get("phase", state["currentPhase"])
        if phase not in PHASES:
            raise WorkflowError("Unknown phase")
        tasks = state["phases"][phase]["tasks"]
        operation = args.get("operation", args.get("todo_action", "list"))
        if operation == "reset":
            tasks = [{"text": t, "done": False, "note": ""} for t in TASKS[phase]]
            state["phases"][phase]["tasks"] = tasks
        elif operation == "add":
            if not isinstance(args.get("text"), str) or not args["text"].strip():
                raise WorkflowError("Task text is required")
            tasks.append({"text": args["text"], "done": False, "note": ""})
        elif operation in {"check", "uncheck"}:
            index = args.get("index")
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(tasks):
                raise WorkflowError("Task index out of range")
            tasks[index].update(done=operation == "check", note=str(args.get("note", "")))
        elif operation != "list":
            raise WorkflowError("Unknown todo operation")
        done = sum(bool(t.get("done")) for t in tasks)
        return {"ok": True, "phase": phase, "tasks": tasks, "done": done, "total": len(tasks), "pct": round(100 * done / len(tasks)) if tasks else 0}
    if action == "artifact-add":
        return artifact_add(store, state, args)
    if action == "claim-add":
        text, question, aids = args.get("text"), args.get("question"), args.get("artifact_ids")
        if not isinstance(text, str) or not text.strip() or question not in state["project"]["subproblems"]:
            raise WorkflowError("Claim needs text and a known question")
        if not isinstance(aids, list) or not aids or any(a not in state["artifacts"] or state["artifacts"][a].get("stale") for a in aids):
            raise WorkflowError("Claim must reference current registered evidence")
        cid = args.get("claim_id") or identifier("claim")
        if not isinstance(cid, str) or not re.fullmatch(r"[\w-]{1,80}", cid):
            raise WorkflowError("Invalid claim_id")
        claim = {"claim_id": cid, "text": text, "question": question, "artifact_ids": aids,
                 "locator": args.get("locator"), "support": "requires_independent_review"}
        state["claims"][cid] = claim
        event(state, "claim_registered", {"claim_id": cid})
        return {"ok": True, "claim": claim}
    if action in {"gate-prepare", "gate-record"}:
        gate = args.get("gate")
        if gate not in GATES:
            raise WorkflowError("Unknown gate")
        prereqs(state, gate)
        minimal_run_id = None
        if gate == "P1":
            if action == "gate-prepare":
                runs = [run for run in state["runs"].values() if run.get("phase") == "programming"]
                minimal_run_id = runs[-1]["run_id"] if runs else None
            else:
                submitted = args.get("receipt", {})
                task = state["review_tasks"].get(submitted.get("task_id"), {}) if isinstance(submitted, dict) else {}
                minimal_run_id = task.get("snapshot", {}).get("config", {}).get("minimal_run_id")
        current = snapshot(store.root, state, GATES[gate], gate=gate, minimal_run_id=minimal_run_id)
        if action == "gate-prepare":
            author = args.get("author_id", state["project"]["authorId"])
            if not isinstance(author, str) or not author.strip():
                raise WorkflowError("Review task author must be a nonempty identity")
            failures = gate_check(store, state, gate, minimal_run_id=minimal_run_id)
            if failures:
                raise WorkflowError("Deterministic prerequisites failed: " + "; ".join(failures), "gate_validation")
            task_id = identifier("review")
            task = {"task_id": task_id, "gate": gate, "snapshot_hash": current["hash"], "snapshot": current,
                    "author_id": author.strip(), "created_at": now(), "status": "prepared"}
            state["review_tasks"][task_id] = task
            brief = f"独立只读审核 {gate} {TITLES[gate]}。核对原始证据和模型约束；P0/P1 未解决返回 FAIL，证据不足返回 BLOCKED。审核者不能是作者。"
            if gate == "W2":
                brief += " 必须查看实际渲染页、图表和引用；结构校验不证明排版或科学正确。"
            return {"ok": True, "gate": gate, "task_id": task_id, "snapshot_hash": current["hash"], "brief": brief, "request": task,
                    "identity_notice": "Reviewer identity is declared unless independently attested by the host."}
        receipt = args.get("receipt")
        if not isinstance(receipt, dict):
            raise WorkflowError("receipt must be an object")
        task = state["review_tasks"].get(receipt.get("task_id"))
        if not task or task["gate"] != gate or task["status"] != "prepared":
            raise WorkflowError("Prepare a fresh review task before recording a receipt", "review_task")
        if receipt.get("snapshot_hash") != task["snapshot_hash"] or current["hash"] != task["snapshot_hash"]:
            raise WorkflowError("Review snapshot is stale or mismatched", "review_snapshot")
        from .schema import validate_schema
        validate_schema("gate-receipt.schema.json", receipt)
        reviewer = receipt.get("reviewer_id")
        if not isinstance(reviewer, str) or not reviewer.strip() or reviewer.strip() in {task["author_id"].strip(), state["project"]["authorId"].strip()}:
            raise WorkflowError("Reviewer must be identified and different from the author", "review_identity")
        source = receipt.get("review_source")
        if source not in {"human", "external", "subagent"}:
            raise WorkflowError("Declare human, external or subagent review; self-review cannot pass")
        status = receipt.get("status")
        findings, evidence = receipt.get("findings"), receipt.get("evidence")
        if status not in {"PASS", "FAIL", "BLOCKED"} or not isinstance(findings, list) or not isinstance(evidence, list):
            raise WorkflowError("Invalid receipt status, findings or evidence")
        if any(not isinstance(f, dict) or f.get("level") not in {"P0", "P1", "P2"} or not isinstance(f.get("text"), str) or not f["text"].strip() for f in findings):
            raise WorkflowError("Findings need level P0/P1/P2 and nonempty text")
        if not isinstance(receipt.get("scope"), str) or not receipt["scope"].strip() or not isinstance(receipt.get("rework", ""), str):
            raise WorkflowError("Receipt must explain scope and rework")
        if status == "PASS":
            if any(f["level"] in {"P0", "P1"} for f in findings):
                raise WorkflowError("PASS cannot contain unresolved P0/P1 findings", "review_findings")
            failures = gate_check(store, state, gate, minimal_run_id=minimal_run_id)
            if failures:
                raise WorkflowError("Current deterministic validation failed: " + "; ".join(failures), "gate_validation")
            if not evidence:
                raise WorkflowError("PASS requires inspectable evidence")
        for item in evidence:
            if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
                raise WorkflowError("Evidence needs a file path and SHA-256")
            path = inside(store.root, item["path"])
            rel = path.relative_to(store.root).as_posix()
            if not path.is_file() or digest(path) != item["sha256"] or current["files"].get(rel) != item["sha256"]:
                raise WorkflowError("Evidence file does not match reviewed snapshot", "review_evidence")
        state["gates"][gate].update(status=status.lower(), at=now(), receipt=deepcopy(receipt), snapshot_hash=current["hash"],
                                     snapshot=current, identity_assurance="declared", invalidation_reason=None)
        task["status"] = "recorded"
        if status != "PASS":
            state["completed"] = False
            state["completedAt"] = None
            for downstream in list(GATES)[list(GATES).index(gate) + 1:]:
                if state["gates"][downstream]["status"] == "pass":
                    state["gates"][downstream].update(status="invalidated", invalidation_reason="Prerequisite review no longer passes")
        event(state, "gate_record", {"gate": gate, "status": status, "reviewer_id": reviewer, "review_source": source})
        return {"ok": True, "gate": gate, "status": status.lower(), "identity_assurance": "declared"}
    if action in {"validate", "complete"}:
        phases = [args.get("phase", state["currentPhase"])] if action == "validate" else list(dict.fromkeys(GATES[g] for g in required_gates(state)))
        results = {phase: phase_validation(store.root, state, phase, load_profile(state["project"]["profile"])) for phase in phases}
        state["deliverables"] = {"at": now(), "results": results}
        if action == "validate":
            result = results[phases[0]]
            if result["overall"] != "ok":
                state["completed"] = False
                state["completedAt"] = None
            return result
        blockers = ["Gate " + g + ": " + state["gates"][g]["status"] for g in required_gates(state) if state["gates"][g]["status"] != "pass"]
        blockers += [phase + ": " + result["overall"] for phase, result in results.items() if result["overall"] != "ok"]
        blockers += ["Run " + identifier + ": running" for identifier, run in state["runs"].items() if run.get("status") == "running"]
        state["completed"] = not blockers
        state["completedAt"] = (state["completedAt"] or now()) if not blockers else None
        state["blockers"] = blockers
        event(state, "completion_checked", {"done": not blockers, "blockers": blockers})
        return {"ok": True, "done": not blockers, "blockers": blockers, "deliverableChecks": {p: r["overall"] for p, r in results.items()}, "validation": results}
    if action == "log":
        event(state, str(args.get("event", "note")), args.get("detail"))
        return {"ok": True}
    if action == "run-log-read":
        run_id = args.get("run_id", "")
        stream = args.get("stream", "stdout")
        limit = args.get("max_bytes", 65536)
        if not isinstance(run_id, str) or not re.fullmatch(r"run_[a-f0-9]{16}", run_id) or run_id not in state["runs"]:
            raise WorkflowError("Unknown recorded run")
        if stream not in {"stdout", "stderr"} or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 262144:
            raise WorkflowError("stream must be stdout/stderr and max_bytes between 1 and 262144")
        relative = ".math-modeling/runs/" + run_id + "/" + stream + ".log"
        path = inside(store.root, relative, metadata=True)
        if not path.is_file():
            raise WorkflowError("This run has no " + stream + " log yet", "log_missing")
        with path.open("rb") as handle:
            raw = handle.read(limit)
        size = path.stat().st_size
        return {"ok": True, "run_id": run_id, "stream": stream, "path": relative, "content": raw.decode("utf-8", errors="replace"), "truncated": size > limit, "bytes": size, "sha256": digest(path)}
    if action == "artifact-read":
        artifact = state["artifacts"].get(args.get("artifact_id"))
        if artifact is None and args.get("path"):
            relative = inside(store.root, args["path"]).relative_to(store.root).as_posix()
            artifact = next((a for a in state["artifacts"].values() if a["path"] == relative), None)
        if artifact is None:
            raise WorkflowError("Only registered artifacts can be previewed")
        path = inside(store.root, artifact["path"])
        limit = args.get("max_bytes", 65536)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 262144:
            raise WorkflowError("max_bytes must be between 1 and 262144")
        with path.open("rb") as stream:
            raw = stream.read(limit)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        textual = path.suffix.lower() in {".md", ".txt", ".csv", ".tsv", ".json", ".py", ".m", ".tex", ".bib", ".log"}
        return {"ok": True, "artifact_id": artifact["artifact_id"], "path": artifact["path"], "sha256": digest(path),
                "mime_type": mime, "bytes": path.stat().st_size, "truncated": path.stat().st_size > limit,
                "content": raw.decode("utf-8", errors="replace") if textual else None,
                "notice": "Binary previews must use the host's authorized file viewer." if not textual else None}
    if action.startswith("checkpoint-"):
        from .checkpoints import checkpoint_action
        return checkpoint_action(store, state, action, args)
    raise WorkflowError("Unknown action: " + action)


def dispatch(args):
    if not isinstance(args, dict) or not isinstance(args.get("action"), str):
        raise WorkflowError("Request requires an action")
    action = args["action"]
    if action == "doctor" and not args.get("project_root"):
        return doctor(args.get("features"))
    if not args.get("project_root"):
        raise WorkflowError("project_root is required")
    skill = args.get("skill_root") or Path(__file__).resolve().parents[1]
    store = Store(args["project_root"], skill)
    if action == "run":
        from .execution import run_action
        return run_action(store, args)
    with store.locked():
        state = store.load()
        persisted = deepcopy(state)
        if action == "init" and state is None:
            state = fresh_state(store, args)
            event(state, "initialized", {"scope": state["project"]["scope"]})
            result = {"ok": True, "resumed": False}
        elif state is None:
            if action == "state":
                return {"ok": True, "initialized": False, "completed": False}
            raise WorkflowError("Initialize this project first", "not_initialized")
        else:
            state = migrate(store, state)
            invalidate(store, state)
            # Persist invalidation even when the requested transition is rejected.
            if action == "init":
                result = {"ok": True, "resumed": True}
            else:
                try:
                    result = execute_action(store, state, action, args)
                except WorkflowError:
                    projection(state)
                    store.save(state)
                    raise
        projection(state)
        if action not in {"state", "checkpoint-list"} or state != persisted:
            store.save(state)
        if action == "state":
            result = {"ok": True, **state}
        elif action in {"init", "complete", "phase"}:
            result = {**state, **result, "revision": state["revision"]}
        else:
            result["revision"] = state["revision"]
        return result
