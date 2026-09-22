#!/usr/bin/env python3
"""Inspect or explicitly prepare directory inheritance for the DSH Windows sandbox.

The default operation is read-only. Applying prepares immediate project roots,
after backing up their security descriptors. It never propagates into subtrees.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys

CREATOR_OWNER_ACE = "(A;CINPIO;WO;;;CO)"


def dacl_parts(sddl: str) -> tuple[str, list[str], str]:
    start = re.search(r"D:[A-Z]*", sddl)
    if start is None or "D:NO_ACCESS_CONTROL" in sddl:
        raise ValueError("A real DACL is required; NULL-DACL preparation is unsupported")
    end = sddl.find("S:", start.end())
    end = len(sddl) if end < 0 else end
    body = sddl[start.end():end]
    aces = re.findall(r"\([^()]*\)", body)
    if "".join(aces) != body:
        raise ValueError("Conditional or unrecognized ACL syntax requires manual review")
    return sddl[:start.end()], aces, sddl[end:]


def ace_key(ace: str) -> tuple:
    parts = ace[1:-1].split(";")
    if len(parts) != 6:
        raise ValueError("Unrecognized ACE syntax requires manual review")
    kind, flags, rights, object_type, inherited_type, trustee = parts
    rights = "WO" if rights.lower() in {"wo", "0x80000", "0x00080000"} else rights
    trustee = "CO" if trustee == "S-1-3-0" else trustee
    return kind, frozenset(re.findall(r"..", flags)), rights, object_type, inherited_type, trustee


def insert_allow(sddl: str, ace: str) -> str:
    prefix, aces, suffix = dacl_parts(sddl)
    position, phase = 0, 0
    for index, existing in enumerate(aces):
        kind, flags, *_ = ace_key(existing)
        if "ID" in flags:
            stage = 2
        elif kind in {"D", "OD", "XD", "ZD"}:
            stage = 0
        elif kind in {"A", "OA", "XA", "ZA"}:
            stage = 1
        else:
            raise ValueError("Unrecognized DACL ACE type requires manual review")
        if stage < phase:
            raise ValueError("Noncanonical DACL requires manual review; no ACEs reordered")
        phase = stage
        if stage == 0:
            position = index + 1
    aces.insert(position, ace)
    return prefix + "".join(aces) + suffix


def remove_recorded_ace(sddl: str, ace: str) -> tuple[str, bool]:
    prefix, aces, suffix = dacl_parts(sddl)
    matches = [index for index, value in enumerate(aces) if ace_key(value) == ace_key(ace)]
    if len(matches) > 1:
        raise ValueError("Duplicate recorded ACE requires manual review")
    if not matches:
        return sddl, False
    del aces[matches[0]]
    return prefix + "".join(aces) + suffix, True


def has_rule(sddl: str) -> bool:
    return any(ace_key(ace) == ace_key(CREATOR_OWNER_ACE) for ace in dacl_parts(sddl)[1])


def denies_write_owner(sddl: str, *, inheritable_only: bool = False) -> bool:
    for ace in dacl_parts(sddl)[1]:
        kind, flags, rights, *_ = ace_key(ace)
        if kind not in {"D", "OD", "XD", "ZD"} or (inheritable_only and "CI" not in flags):
            continue
        if any(flag in rights for flag in ("WO", "GA", "FA")) or (rights.lower().startswith("0x") and int(rights, 16) & 0x10080000):
            return True
    return False


def insert_rule(sddl: str) -> str:
    if has_rule(sddl):
        return sddl
    return insert_allow(sddl, CREATOR_OWNER_ACE)


class WindowsSecurity:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("This helper requires Windows; no changes were made")
        from ctypes import wintypes as w
        self.w = w
        self.api = ctypes.WinDLL("advapi32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        pointer = ctypes.c_void_p
        self.api.GetNamedSecurityInfoW.argtypes = [w.LPWSTR, ctypes.c_int, w.DWORD, pointer, pointer, pointer, pointer, ctypes.POINTER(pointer)]
        self.api.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [pointer, w.DWORD, w.DWORD, ctypes.POINTER(pointer), ctypes.POINTER(w.DWORD)]
        self.api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(pointer), pointer]
        self.api.GetSecurityDescriptorDacl.argtypes = [pointer, ctypes.POINTER(w.BOOL), ctypes.POINTER(pointer), ctypes.POINTER(w.BOOL)]
        self.api.SetNamedSecurityInfoW.argtypes = [w.LPWSTR, ctypes.c_int, w.DWORD, pointer, pointer, pointer, pointer]
        self.api.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, pointer]
        self.api.SetFileSecurityW.restype = w.BOOL
        self.api.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
        self.api.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, pointer, w.DWORD, ctypes.POINTER(w.DWORD)]
        self.api.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(pointer)]
        self.kernel.GetCurrentProcess.restype = w.HANDLE
        self.kernel.LocalFree.argtypes = [pointer]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, pointer, w.DWORD, w.DWORD, w.HANDLE]
        self.kernel.CreateFileW.restype = w.HANDLE

    def current_user_sid(self) -> str:
        token, size, string = self.w.HANDLE(), self.w.DWORD(), ctypes.c_void_p()
        if not self.api.OpenProcessToken(self.kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.api.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            data = ctypes.create_string_buffer(size.value)
            if not self.api.GetTokenInformation(token, 1, data, size.value, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            sid = ctypes.c_void_p.from_buffer(data)
            if not self.api.ConvertSidToStringSidW(sid, ctypes.byref(string)):
                raise ctypes.WinError(ctypes.get_last_error())
            return ctypes.wstring_at(string)
        finally:
            if string:
                self.kernel.LocalFree(string)
            self.kernel.CloseHandle(token)

    def read(self, path: Path) -> str:
        sd, string, size = ctypes.c_void_p(), ctypes.c_void_p(), self.w.DWORD()
        status = self.api.GetNamedSecurityInfoW(str(path), 1, 0x17, None, None, None, None, ctypes.byref(sd))
        if status:
            raise OSError(status, "Read security descriptor failed", str(path))
        try:
            if not self.api.ConvertSecurityDescriptorToStringSecurityDescriptorW(sd, 1, 0x17, ctypes.byref(string), ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            return ctypes.wstring_at(string)
        finally:
            if string:
                self.kernel.LocalFree(string)
            if sd:
                self.kernel.LocalFree(sd)

    def access(self, path: Path) -> dict:
        result = {}
        for name, mask in [("WRITE_DAC", 0x40000), ("WRITE_OWNER", 0x80000)]:
            handle = self.kernel.CreateFileW(str(path), mask, 7, None, 3, 0x02000000, None)
            granted = handle != ctypes.c_void_p(-1).value
            result[name] = {"granted": granted, "win32_error": 0 if granted else ctypes.get_last_error()}
            if granted:
                self.kernel.CloseHandle(handle)
        return result

    def set_dacl(self, path: Path, sddl: str) -> None:
        sd, acl = ctypes.c_void_p(), ctypes.c_void_p()
        present, defaulted = self.w.BOOL(), self.w.BOOL()
        if not self.api.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.GetSecurityDescriptorDacl(sd, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not present or not acl:
                raise ValueError("A real DACL is required")
            # Unlike SetNamedSecurityInfoW, this API does not propagate into
            # existing descendants. Newly created children still inherit ACEs.
            if not self.api.SetFileSecurityW(str(path), 4, sd):
                raise OSError(ctypes.get_last_error(), "Set DACL failed; inspect backup before retrying", str(path))
        finally:
            self.kernel.LocalFree(sd)


def is_reparse(path: Path) -> bool:
    return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def verify_target(root: Path, path: Path, expected: str, security: WindowsSecurity) -> None:
    if path != root and path.parent != root:
        raise ValueError("Only immediate project roots may be changed")
    for part in [path, *path.parents]:
        if is_reparse(part):
            raise ValueError(f"Reparse path refused before mutation: {part}")
    current = security.read(path)
    if current != expected:
        raise RuntimeError(f"ACL changed before mutation: {path}; inspect backup before retrying")
    owner = re.search(r"O:(.*?)(?=G:|D:|S:|$)", current)
    if not owner or owner.group(1) != security.current_user_sid():
        raise ValueError("Directory ownership changed before mutation")


def validate_parent(raw: str, security: WindowsSecurity) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute() or str(path).startswith("\\\\"):
        raise ValueError("Use an absolute local workspace-parent directory")
    if not path.is_dir():
        raise ValueError("workspace-parent must be an existing directory")
    for part in [path, *path.parents]:
        if is_reparse(part):
            raise ValueError(f"Reparse path refused: {part}")
    path = path.resolve()
    blocked = [Path(path.anchor), Path.home(), Path.home().parent]
    system_trees = [Path(value).resolve() for name in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData") if (value := os.environ.get(name))]
    if path in blocked or any(path == base or path.is_relative_to(base) for base in system_trees):
        raise ValueError("Drive roots, home roots and system directories are not workspace parents")
    sddl = security.read(path)
    owner = re.search(r"O:(.*?)(?=G:|D:|S:|$)", sddl)
    if not owner or owner.group(1) != security.current_user_sid():
        raise ValueError("The current user must own workspace-parent")
    if not security.access(path)["WRITE_DAC"]["granted"]:
        raise ValueError("workspace-parent requires existing WRITE_DAC access")
    return path, sddl


def snapshot_directories(root: Path, security: WindowsSecurity) -> tuple[list[dict], list[dict]]:
    entries, skipped, paths = [], [], [root]
    current_user = security.current_user_sid()
    with os.scandir(root) as children:
        for child in children:
            if child.is_dir(follow_symlinks=False) or is_reparse(Path(child.path)):
                paths.append(Path(child.path))
    for path in paths:
        if is_reparse(path) or (path != root and path.resolve().parent != root):
            raise ValueError(f"Reparse or escaping directory refused: {path}")
        sddl = security.read(path)
        owner = re.search(r"O:(.*?)(?=G:|D:|S:|$)", sddl)
        record = {"relative_path": "." if path == root else path.name, "owner": owner.group(1) if owner else None, "sddl": sddl, "access": security.access(path)}
        entries.append(record)
        control = re.search(r"D:([A-Z]*)", sddl)
        if path != root and control and "P" in control.group(1):
            skipped.append({"relative_path": record["relative_path"], "reason": "protected inheritance; unchanged"})
            continue
        if path != root and record["owner"] != current_user:
            skipped.append({"relative_path": record["relative_path"], "reason": "not owned by current user; unchanged"})
        elif path != root and denies_write_owner(sddl):
            skipped.append({"relative_path": record["relative_path"], "reason": "WRITE_OWNER deny requires manual review; unchanged"})
    return entries, skipped


def prepare(args: argparse.Namespace, security: WindowsSecurity) -> dict:
    root, before = validate_parent(args.workspace_parent, security)
    entries, skipped, updates = [], [], []
    if not args.rollback:
        entries, skipped = snapshot_directories(root, security)
        excluded = {entry["relative_path"] for entry in skipped}
        if not has_rule(before):
            if denies_write_owner(before):
                raise ValueError("A WRITE_OWNER deny requires manual review")
            updates.append({"path": root, "before": before, "after": insert_rule(before), "added_ace": CREATOR_OWNER_ACE})
        for entry in entries[1:]:
            if entry["relative_path"] in excluded or entry["access"]["WRITE_OWNER"]["granted"]:
                continue
            ace = f"(A;;WO;;;{entry['owner']})"
            value = entry["sddl"]
            updates.append({"path": root / entry["relative_path"], "before": value, "after": insert_allow(value, ace), "added_ace": ace})
    result = {"ok": True, "workspace_parent": str(root), "mode": "apply" if args.apply else "read-only", "changed": False, "rule": CREATOR_OWNER_ACE, "current_rule_present": has_rule(before), "root_access": security.access(root), "effect": "Future immediate project directories inherit CREATOR OWNER WRITE_OWNER; eligible existing immediate roots gain owner-only WRITE_OWNER. No recursive propagation; parent itself, files and deeper existing directories gain no rights.", "planned_directories": [str(item["path"]) for item in updates], "skipped": skipped}
    if args.rollback:
        source = Path(args.rollback)
        if not source.is_absolute() or not source.is_file() or source.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("--rollback requires an absolute backup JSON file up to 8 MiB")
        for part in [source, *source.parents]:
            if is_reparse(part):
                raise ValueError("Reparse rollback file refused")
        original = json.loads(source.read_text(encoding="utf-8"))
        if original.get("format_version") != 2 or original.get("workspace_parent") != str(root) or original.get("operation") != "apply":
            raise ValueError("Rollback requires this parent's version-2 apply backup with recorded added ACEs")
        updates, seen = [], set()
        originals = {entry["relative_path"]: entry for entry in original["entries"]}
        for change in original["changes"]:
            name = change["relative_path"]
            if not isinstance(name, str) or name in seen or (name != "." and (name in {"", ".."} or any(char in name for char in '/\\:'))):
                raise ValueError("Rollback entries must be unique immediate directory names")
            seen.add(name)
            path = root if name == "." else root / name
            current = security.read(path)
            verify_target(root, path, current, security)
            old = originals[name]
            expected_ace = CREATOR_OWNER_ACE if name == "." else f"(A;;WO;;;{old['owner']})"
            if ace_key(change["added_ace"]) != ace_key(expected_ace):
                raise ValueError("Backup contains an unsupported added ACE")
            if any(ace_key(ace) == ace_key(expected_ace) for ace in dacl_parts(old["sddl"])[1]):
                raise ValueError("Rollback must not remove a pre-existing ACE")
            revised, removed = remove_recorded_ace(current, expected_ace)
            entries.append({"relative_path": name, "owner": security.current_user_sid(), "sddl": current, "access": security.access(path)})
            if removed:
                updates.append({"path": path, "before": current, "after": revised, "removed_ace": expected_ace})
        result.update(mode="rollback", planned_directories=[str(item["path"]) for item in updates], rollback_source=str(source), inherited_grants_on_later_created_projects_retained=True)
    if (not args.apply and not args.rollback) or not updates:
        return result
    # Set the parent last: on some Windows versions a child read can refresh
    # its inheritance after the parent changes, invalidating the saved check.
    updates.sort(key=lambda item: item["path"] == root)
    if not args.backup:
        raise ValueError("A changed --apply or --rollback requires --backup with a new absolute JSON file")
    backup = Path(args.backup)
    if not backup.is_absolute() or backup.exists() or not backup.parent.is_dir():
        raise ValueError("--backup must be a new absolute file in an existing directory")
    for part in [backup.parent, *backup.parent.parents]:
        if is_reparse(part):
            raise ValueError("Reparse backup path refused")
    changes = [{"relative_path": "." if item["path"] == root else item["path"].name, **{key: item[key] for key in ("added_ace", "removed_ace") if key in item}} for item in updates]
    record = {"format_version": 2, "operation": "rollback" if args.rollback else "apply", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "workspace_parent": str(root), "security_information": "OWNER|GROUP|DACL|LABEL", "proposed_ace": CREATOR_OWNER_ACE, "entries": entries, "changes": changes, "skipped": skipped}
    encoded = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with backup.open("xb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    for update in updates:
        verify_target(root, update["path"], update["before"], security)
    applied = []
    try:
        for update in updates:
            verify_target(root, update["path"], update["before"], security)
            security.set_dacl(update["path"], update["after"])
            applied.append(update["path"])
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Partial apply stopped after {len(applied)} directories; backup: {backup}; {exc}") from exc
    after = security.read(root)
    if not args.rollback and not has_rule(after):
        raise RuntimeError(f"ACL verification failed; inspect backup {backup}")
    for update in updates:
        if not args.rollback and update["path"] != root and not security.access(update["path"])["WRITE_OWNER"]["granted"]:
            raise RuntimeError(f"WRITE_OWNER verification failed for {update['path']}; inspect backup {backup}")
    result.update(changed=True, current_rule_present=has_rule(after), backup=str(backup), backup_sha256=hashlib.sha256(encoded).hexdigest(), backed_up_directories=len(entries), applied_directories=[str(p) for p in applied], root_access_after=security.access(root))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-parent", required=True)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--apply", action="store_true", help="Explicitly add the directory inheritance rule after backup")
    operation.add_argument("--rollback", help="Version-2 apply backup whose recorded explicit ACEs should be removed")
    parser.add_argument("--backup", help="New absolute JSON backup filename; required for a changed apply")
    args = parser.parse_args(argv)
    try:
        report = prepare(args, WindowsSecurity())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
