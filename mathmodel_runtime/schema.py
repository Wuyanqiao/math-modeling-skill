"""Validate the bundled JSON Schema subset without optional dependencies or network refs."""
import json
import math
from pathlib import Path
import re

from .storage import WorkflowError

ROOT = Path(__file__).parent / "resources" / "schemas"
KEYWORDS = {"$schema", "$id", "$ref", "title", "description", "type", "required", "properties", "additionalProperties", "items", "minItems", "uniqueItems", "enum", "const", "pattern", "minLength", "minimum"}


def validate_schema(name, value):
    """Enforce all keywords used by bundled schemas; reject unsupported constraints."""
    def check(node, item, location):
        unknown = set(node) - KEYWORDS
        if unknown:
            raise WorkflowError("Unsupported schema constraints: " + ", ".join(sorted(unknown)), "schema_definition")
        if "$ref" in node:
            reference = node["$ref"]
            target = ROOT / reference
            if not isinstance(reference, str) or target.name != reference or not target.is_file():
                raise WorkflowError("Only bundled local schema references are allowed", "schema_definition")
            check(json.loads(target.read_text(encoding="utf-8")), item, location)
            return
        types = {
            "object": isinstance(item, dict), "array": isinstance(item, list), "string": isinstance(item, str),
            "integer": isinstance(item, int) and not isinstance(item, bool),
            "number": isinstance(item, (int, float)) and not isinstance(item, bool) and (not isinstance(item, float) or math.isfinite(item)),
            "boolean": isinstance(item, bool), "null": item is None,
        }
        expected = node.get("type")
        if expected and not any(types.get(t, False) for t in ([expected] if isinstance(expected, str) else expected)):
            raise WorkflowError(f"{location}: expected {expected}", "schema_validation")
        if "const" in node and (item != node["const"] or type(item) is not type(node["const"])):
            raise WorkflowError(location + ": wrong constant", "schema_validation")
        if "enum" in node and item not in node["enum"]:
            raise WorkflowError(location + ": value is outside the supported enum", "schema_validation")
        if isinstance(item, dict):
            missing = set(node.get("required", [])) - item.keys()
            if missing:
                raise WorkflowError(location + ": missing " + ", ".join(sorted(missing)), "schema_validation")
            for key, child in item.items():
                definition = node.get("properties", {}).get(key, node.get("additionalProperties", True))
                if definition is False:
                    raise WorkflowError(location + ": unsupported field " + key, "schema_validation")
                if isinstance(definition, dict):
                    check(definition, child, location + "." + key)
        if isinstance(item, list):
            if len(item) < node.get("minItems", 0):
                raise WorkflowError(location + ": too few items", "schema_validation")
            if node.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in item}) != len(item):
                raise WorkflowError(location + ": duplicate items", "schema_validation")
            for i, child in enumerate(item):
                if "items" in node:
                    check(node["items"], child, f"{location}[{i}]")
        if isinstance(item, str):
            if len(item) < node.get("minLength", 0) or ("pattern" in node and not re.search(node["pattern"], item)):
                raise WorkflowError(location + ": invalid string", "schema_validation")
        if "minimum" in node and (not isinstance(item, (int, float)) or item < node["minimum"]):
            raise WorkflowError(location + ": below minimum", "schema_validation")
    path = ROOT / name
    if path.name != name or not path.is_file():
        raise WorkflowError("Unknown bundled schema", "schema_definition")
    check(json.loads(path.read_text(encoding="utf-8")), value, name)


def validate_state(state):
    validate_schema("state.schema.json", state)
    from .storage import GATES, PHASES
    if set(state["gates"]) != set(GATES) or set(state["phases"]) != set(PHASES):
        raise WorkflowError("State is missing or has unknown phases/gates", "state_corrupt")
    if state.get("currentPhase") not in PHASES or not isinstance(state.get("ledger"), list):
        raise WorkflowError("State phase or ledger is invalid", "state_corrupt")
    for phase in state["phases"].values():
        if not isinstance(phase, dict) or not isinstance(phase.get("tasks"), list):
            raise WorkflowError("State task list is invalid", "state_corrupt")
        if any(not isinstance(task, dict) or not isinstance(task.get("text"), str) or not isinstance(task.get("done"), bool) for task in phase["tasks"]):
            raise WorkflowError("State task entry is invalid", "state_corrupt")
    for name, gate in state["gates"].items():
        if not isinstance(gate, dict) or gate.get("status") not in {"pending", "pass", "fail", "blocked", "invalidated"}:
            raise WorkflowError("State gate is invalid: " + name, "state_corrupt")
        if gate["status"] == "pass":
            receipt = gate.get("receipt")
            validate_schema("gate-receipt.schema.json", receipt)
            task = state["review_tasks"].get(receipt["task_id"], {})
            if receipt["status"] != "PASS" or task.get("status") != "recorded" or task.get("gate") != name or not gate.get("snapshot_hash") or receipt["snapshot_hash"] != gate["snapshot_hash"] or task.get("snapshot_hash") != gate["snapshot_hash"]:
                raise WorkflowError("PASS gate lacks a matching recorded review: " + name, "state_corrupt")
            if not receipt["evidence"] or any(item["level"] in {"P0", "P1"} for item in receipt["findings"]) or receipt["reviewer_id"].strip() in {str(task.get("author_id", "")).strip(), state["project"]["authorId"].strip()}:
                raise WorkflowError("PASS gate contains an invalid independent review: " + name, "state_corrupt")
