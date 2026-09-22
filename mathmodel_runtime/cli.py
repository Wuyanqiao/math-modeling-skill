"""Structured CLI shared by local agents and DSH host tools."""

import argparse
import base64
import json
import sys

from .engine import dispatch
from .storage import WorkflowError
from . import __version__


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Math Modeling Workbench runtime")
    parser.add_argument("action", nargs="?")
    parser.add_argument("--project-root")
    parser.add_argument("--skill-root")
    parser.add_argument("--options", default="{}", help="JSON object of action parameters")
    parser.add_argument("--request-base64", help="Base64-encoded UTF-8 JSON request; use - to read at most 2 MiB from stdin")
    parser.add_argument("--version", action="version", version="mathmodel " + __version__)
    args = parser.parse_args(argv)
    try:
        if args.request_base64:
            encoded = args.request_base64
            if encoded == "-":
                encoded = sys.stdin.read(2 * 1024 * 1024 + 1)
                if len(encoded) > 2 * 1024 * 1024:
                    raise WorkflowError("Encoded stdin request exceeds the 2 MiB limit")
            request = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
        else:
            request = json.loads(args.options)
            if not isinstance(request, dict):
                raise WorkflowError("--options must be an object")
            request["action"] = args.action
            if args.project_root:
                request["project_root"] = args.project_root
            if args.skill_root:
                request["skill_root"] = args.skill_root
        result = dispatch(request)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result.get("ok") else 1
    except (WorkflowError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "code": getattr(exc, "code", "invalid_request")}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
