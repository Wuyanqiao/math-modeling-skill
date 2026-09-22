"""Backward-compatible project preferences shared by hosts and local agents."""
from copy import deepcopy

from .storage import WorkflowError


BASE_GRAPHICS = ("scientific-visualization", "matplotlib")
OPTIONAL_GRAPHICS = ("scienceplots", "drawio", "scientific-schematics", "scivis-agent-skills", "seaborn")
COLLABORATION = ("rulesCheck", "attachmentInventory", "literature", "prototype", "experiments", "bilingual", "terminology")
ALIASES = {"paperFormat": "paper_format", "optionalCollab": "optional_collab", "graphicsTools": "graphics_tools", "paperRequirements": "paper_requirements"}
SETTINGS = {"title", "scope", "profile", "paper_format", "subproblems", "competition", "edition", "rules", "optional_collab", "graphics_tools", "paper_requirements"}


def text_setting(value, name, limit, *, empty=True):
    if not isinstance(value, str) or "\x00" in value or len(value) > limit or (not empty and not value.strip()):
        raise WorkflowError(f"{name} must be {'nonempty ' if not empty else ''}text of at most {limit} characters")
    return value


def graphics_options(value=None):
    result = {**dict.fromkeys(BASE_GRAPHICS, True), **dict.fromkeys(OPTIONAL_GRAPHICS, False)}
    if isinstance(value, list):
        if any(not isinstance(name, str) for name in value) or len(value) != len(set(value)):
            raise WorkflowError("graphics_tools must contain distinct tool names")
        value = dict.fromkeys(value, True)
    if value is not None:
        if not isinstance(value, dict) or set(value) - result.keys() or any(not isinstance(enabled, bool) for enabled in value.values()):
            raise WorkflowError("graphics_tools must map supported tool names to booleans")
        if any(value.get(name) is False for name in BASE_GRAPHICS):
            raise WorkflowError("scientific-visualization and matplotlib are required baseline tools")
        result.update(value)
    return result


def paper_requirements(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {"text", "source"}:
        raise WorkflowError("paper_requirements must contain text and source")
    text = text_setting(value.get("text", ""), "paper_requirements.text", 30000)
    source = text_setting(value.get("source", ""), "paper_requirements.source", 2000)
    if text.strip() and not source.strip():
        raise WorkflowError("Nonempty paper requirements need a user instruction or official source")
    return {"text": text, "source": source}


def legacy_paper_requirements(value):
    """Preserve old free text without claiming it came from verified rules."""
    return paper_requirements({"text": value, "source": "旧版项目字段（来源未核实）" if value.strip() else ""})


def configure_project(store, state, args):
    from .engine import fresh_state

    supplied = args.get("settings")
    if not isinstance(supplied, dict) or not supplied:
        raise WorkflowError("configure requires a nonempty settings object")
    settings = {}
    for key, value in supplied.items():
        key = ALIASES.get(key, key)
        if key not in SETTINGS or key in settings:
            raise WorkflowError("Unsupported or duplicate project setting: " + key)
        settings[key] = value
    if any(run.get("status") == "running" for run in state["runs"].values()):
        raise WorkflowError("Project configuration cannot change during a running execution", "run_active")
    project = state["project"]
    names = {"paper_format": "paperFormat", "optional_collab": "optionalCollab", "graphics_tools": "graphicsTools", "paper_requirements": "paperRequirements"}
    current = {key: deepcopy(project.get(names.get(key, key))) for key in SETTINGS}
    for key in ("optional_collab", "graphics_tools"):
        if isinstance(settings.get(key), dict):
            settings[key] = {**(current[key] or {}), **settings[key]}
    current.update(settings)
    current["author_id"] = project["authorId"]
    candidate = fresh_state(store, current)["project"]
    changed = {names.get(key, key): candidate[names.get(key, key)] for key in settings if project.get(names.get(key, key)) != candidate[names.get(key, key)]}
    if "subproblems" in changed:
        questions = set(changed["subproblems"])
        if any(item.get("question") and item["question"] not in questions for kind in ("artifacts", "claims") for item in state[kind].values()):
            raise WorkflowError("Cannot remove a subproblem referenced by existing claims or artifacts")
    project.update(changed)
    if project["scope"] != "full" and state["currentPhase"] != project["scope"]:
        state["currentPhase"] = project["scope"]
    return {"ok": True, "changed": sorted(changed), "project": deepcopy(project)}
