"""Platform shim (local patch): the CapCut auto-reload companion is Windows-only.
On other platforms drafts still save normally; auto-reload just reports it's unsupported."""
import sys

if sys.platform == "win32":
    from _desktop_companion_win import *  # noqa: F401,F403
else:
    def get_capcut_windows():
        return []

    def reload_capcut_desktop(project_name=None, delay=0.35):
        return {"success": False, "action": "unsupported",
                "message": "CapCut desktop auto-reload is only supported on Windows.", "elapsed_seconds": 0}
