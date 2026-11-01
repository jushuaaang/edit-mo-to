"""Close the command window the app opened for this Claude session, once the video is finished (app mode).

    .claude/edit-mo-to/run gui/close_window.py [--delay SECONDS]

Windows only: {tmp}/gui/window.json names the window (cmd /k "claude …") the app's Start / Resume opened. It is closed
only when that window is an ancestor of this process, i.e. the window this very Claude runs in; a window the app opened
for another session, or a Claude started by hand, is never touched. The close runs detached after --delay seconds
(default 5), so Claude's last message reaches the screen first. Prints one JSON line: {"ok": true, "closing": pid} or
{"ok": true, "closing": null, "why": "..."}.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobstate as js  # noqa: E402


def _parents() -> dict:
    """{pid: parent pid} for every running process (Windows Toolhelp snapshot)."""
    import ctypes
    from ctypes import wintypes

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        return {}
    out = {}
    try:
        pe = PE()
        pe.dwSize = ctypes.sizeof(PE)
        ok = k32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            out[pe.th32ProcessID] = pe.th32ParentProcessID
            ok = k32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        k32.CloseHandle(snap)
    return out


def is_ancestor(pid: int, me: int, parents: dict) -> bool:
    """True when pid is me or one of my ancestors (a parent loop or a missing link ends the walk)."""
    seen = set()
    while me and me not in seen:
        if me == pid:
            return True
        seen.add(me)
        me = parents.get(me, 0)
    return False


def main(argv: "list[str]") -> dict:
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--delay", type=int, default=5)
    a = a.parse_args(argv)
    if sys.platform != "win32":
        return {"closing": None, "why": "only Windows can tell which window is Claude's; close Terminal yourself"}
    try:
        pid = json.loads((js.gui_dir() / "window.json").read_text(encoding="utf-8")).get("pid")
    except (OSError, ValueError, AttributeError):
        return {"closing": None, "why": "the app opened no window (Claude was started by hand)"}
    import os
    if not isinstance(pid, int) or not is_ancestor(pid, os.getpid(), _parents()):
        return {"closing": None, "why": "this Claude is not in the window the app opened"}
    delay = max(0, min(a.delay, 60))
    # started through WMI, so the closer is not in the window's process tree (taskkill /T would end it half-way)
    line = f"cmd /c timeout /t {delay} /nobreak >nul & taskkill /PID {pid} /T /F >nul"
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
                        f"-Arguments @{{CommandLine='{line}'}} | Select-Object -ExpandProperty ReturnValue"],
                       capture_output=True, text=True, timeout=30, creationflags=0x08000000)
    if r.returncode != 0 or r.stdout.strip() != "0":
        return {"closing": None, "why": "Windows would not start the closer; close the window yourself"}
    return {"closing": pid}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"ok": True, **main(sys.argv[1:])}, ensure_ascii=False))
