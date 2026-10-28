"""Who may see "Generate for me" (spec "Generate for me (Joshua only, 2026-10-28)"). Standard library only.

    generate_allowed()       True only when machine.json has "generate_for_me": true AND the signed-in Claude Code
                             account's email is in its "generate_for_me_accounts" list (case-insensitive). Anything
                             else (no switch, no list, logged out, an unreadable file, another account) is False.
    claude_account_email()   oauthAccount.emailAddress from ~/.claude.json (Windows: %USERPROFILE%\\.claude.json), or None.
    elevenlabs_key_set()     True when .claude/edit-mo-to/secrets.json holds a non-empty "elevenlabs_api_key".

It is a convenience gate, not security: it only ever uses the signed-in editor's own Chrome, account and keys. The
email and the key are never returned to a caller outside this module except as these yes/no answers, never printed and
never logged. machine.json is read at call time (machine.CONFIG), so a change needs no restart.
"""
import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import machine  # noqa: E402

SECRETS = Path(machine.CONFIG).parent / "secrets.json"
MAX_CLAUDE_JSON = 64 << 20   # a bigger ~/.claude.json is not read (fail closed)
_cache: dict = {}            # {path: ((mtime_ns, size), email or None)}: the server asks on every page poll


def _home(home=None) -> Path:
    return Path(home) if home is not None else Path.home()


def claude_account_email(home=None) -> "str | None":
    """The signed-in Claude Code account's email, or None on any problem. Only this one field is kept."""
    path = _home(home) / ".claude.json"
    try:
        st = path.stat()
        if not path.is_file() or st.st_size > MAX_CLAUDE_JSON:
            return None
        key = (st.st_mtime_ns, st.st_size)
        hit = _cache.get(str(path))
        if hit and hit[0] == key:
            return hit[1]
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    oauth = data.get("oauthAccount") if isinstance(data, dict) else None
    email = oauth.get("emailAddress") if isinstance(oauth, dict) else None
    email = email.strip() if isinstance(email, str) and email.strip() else None
    _cache[str(path)] = (key, email)
    return email


def _switch() -> "tuple[bool, list]":
    """(generate_for_me is exactly true, the list of account emails) from machine.json; (False, []) on any problem."""
    try:
        data = json.loads(Path(machine.CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, []
    if not isinstance(data, dict) or data.get("generate_for_me") is not True:
        return False, []
    accounts = data.get("generate_for_me_accounts")
    if not isinstance(accounts, list):
        return False, []
    return True, [a.strip().casefold() for a in accounts if isinstance(a, str) and a.strip()]


def generate_allowed(home=None) -> bool:
    on, accounts = _switch()
    if not on or not accounts:
        return False
    email = claude_account_email(home)
    return email is not None and email.casefold() in accounts


def elevenlabs_key_set(path=None) -> bool:
    """Yes/no only: the key itself never leaves this function."""
    try:
        data = json.loads(Path(path if path is not None else SECRETS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    value = data.get("elevenlabs_api_key") if isinstance(data, dict) else None
    return isinstance(value, str) and bool(value.strip())
