"""Lock contention, including a real Windows delete-pending handle."""
from concurrent.futures import ThreadPoolExecutor
import errno
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from mathmodel_runtime import storage
from mathmodel_runtime.engine import dispatch


ROOT = Path(__file__).resolve().parents[1]


class RuntimeLockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime lock ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = storage.Store(self.root, ROOT)

    def test_windows_transient_permission_error_retries_creation_only(self):
        actual_open = os.open
        attempts = 0

        def open_lock(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError(errno.EACCES, "delete pending", str(args[0]))
            return actual_open(*args, **kwargs)

        with patch.object(storage.sys, "platform", "win32"), patch.object(storage.os, "open", side_effect=open_lock):
            with self.store.locked():
                self.assertTrue((self.store.meta / "state.lock").exists())
        self.assertEqual(attempts, 2)
        self.assertFalse((self.store.meta / "state.lock").exists())

    def test_persistent_windows_permission_error_keeps_original_error_and_deadline(self):
        denial = PermissionError(errno.EACCES, "permanent ACL denial")
        with patch.object(storage.sys, "platform", "win32"), patch.object(storage.os, "open", side_effect=denial) as opened:
            with patch.object(storage.time, "monotonic", side_effect=[100., 100., 105.]), patch.object(storage.time, "sleep") as slept:
                with self.assertRaises(PermissionError) as caught:
                    with self.store.locked():
                        self.fail("Permission denial must not acquire the lock")
        self.assertIs(caught.exception, denial)
        self.assertEqual(opened.call_count, 2)
        slept.assert_called_once_with(.05)

    def test_non_windows_permission_and_unrelated_io_errors_are_not_retried(self):
        for platform, error in (("linux", PermissionError(errno.EACCES, "denied")),
                                ("win32", OSError(errno.ENOSPC, "disk full"))):
            with self.subTest(platform=platform, error=error):
                with patch.object(storage.sys, "platform", platform), patch.object(storage.os, "open", side_effect=error) as opened:
                    with patch.object(storage.time, "sleep") as slept, self.assertRaises(OSError) as caught:
                        with self.store.locked():
                            self.fail("Must not acquire lock")
                self.assertIs(caught.exception, error)
                self.assertEqual(opened.call_count, 1)
                slept.assert_not_called()

    def test_existing_lock_timeout_remains_project_locked(self):
        with patch.object(storage.os, "open", side_effect=FileExistsError(errno.EEXIST, "held lock")):
            with patch.object(storage.time, "monotonic", side_effect=[100., 104.99, 105.]), patch.object(storage.time, "sleep") as slept:
                with self.assertRaises(storage.WorkflowError) as caught:
                    with self.store.locked():
                        self.fail("Must not acquire lock")
        self.assertEqual(caught.exception.code, "project_locked")
        self.assertLessEqual(slept.call_args.args[0], .011)

    def test_lock_metadata_write_failure_is_not_retried_and_releases_owned_lock(self):
        actual_open = os.open
        with patch.object(storage.os, "open", wraps=actual_open) as opened:
            with patch.object(storage.json, "dump", side_effect=PermissionError(errno.EACCES, "write denied")):
                with self.assertRaises(PermissionError):
                    with self.store.locked():
                        self.fail("Metadata failed")
        self.assertEqual(opened.call_count, 1)
        self.assertFalse((self.store.meta / "state.lock").exists())

    @unittest.skipUnless(sys.platform == "win32", "requires real Windows file deletion semantics")
    def test_real_windows_delete_pending_retries_until_last_handle_closes(self):
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel.SetFileInformationByHandle.restype = wintypes.BOOL
        self.store.meta.mkdir()
        lock = self.store.meta / "state.lock"
        lock.write_text("previous holder", encoding="utf-8")
        # OPEN_EXISTING, GENERIC_READ|DELETE, SHARE_READ|WRITE|DELETE.
        handle = kernel.CreateFileW(str(lock), 0x80010000, 7, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        closed = threading.Event()

        def close_handle():
            kernel.CloseHandle(handle)
            closed.set()

        timer = None
        try:
            # Classic FileDispositionInfo (not POSIX FileDispositionInfoEx) keeps
            # deletion pending while this handle is open on current Windows.
            delete_pending = ctypes.c_ubyte(1)
            if not kernel.SetFileInformationByHandle(handle, 4, ctypes.byref(delete_pending), ctypes.sizeof(delete_pending)):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except PermissionError as error:
                self.assertEqual(error.errno, errno.EACCES)
            else:
                os.close(descriptor)
                self.fail("Win32 delete-pending did not reproduce EACCES")
            timer = threading.Timer(.15, close_handle)
            timer.start()
            with self.store.locked():
                self.assertTrue(closed.wait(timeout=1))
                self.assertTrue(lock.exists())
        finally:
            if timer:
                timer.join()
            if not closed.is_set():
                close_handle()
        self.assertFalse(lock.exists())

    def test_concurrent_writes_keep_all_notes_across_repeated_contention(self):
        arguments = {"project_root": str(self.root), "skill_root": str(ROOT)}
        dispatch({**arguments, "action": "init"})
        with ThreadPoolExecutor(max_workers=8) as pool:
            for batch in range(3):
                list(pool.map(lambda index: dispatch({**arguments, "action": "log", "event": "lock-regression", "detail": index}),
                              range(batch * 16, (batch + 1) * 16)))
        state = dispatch({**arguments, "action": "state"})
        notes = [row["detail"] for row in state["ledger"] if row["event"] == "lock-regression"]
        self.assertEqual(sorted(notes), list(range(48)))


if __name__ == "__main__":
    unittest.main()
