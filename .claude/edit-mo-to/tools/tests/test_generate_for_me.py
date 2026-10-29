"""Task G: "Generate for me" (Joshua only): the account gate, the page flag, prefs, job.py can-generate, secrets.json.

Spec "Generate for me (Joshua only, 2026-10-28)". The gate fails closed: the switch in machine.json must be true AND the
signed-in Claude Code account (oauthAccount.emailAddress in ~/.claude.json) must be in generate_for_me_accounts. The
email never reaches the page, a log or a reply.
"""
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
GUI = TOOLS.parent / "gui"
ROOT = TOOLS.parents[2]
for _p in (str(GUI), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import account  # noqa: E402
import jobstate as js  # noqa: E402
import machine  # noqa: E402
import server  # noqa: E402

JOB = GUI / "job.py"
TOKEN = "gen-token-1"
EMAIL = "owner.person@example.com"
OTHER = "someone.else@example.com"


def _home(tmp_path, email=EMAIL, raw=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    body = raw if raw is not None else json.dumps({"numStartups": 3, "projects": {"/x": {"history": ["secret"]}},
                                                   "oauthAccount": {"emailAddress": email, "displayName": "Owner"}})
    (home / ".claude.json").write_text(body, encoding="utf-8")
    return home


def _machine(tmp_path, monkeypatch, **cfg):
    path = tmp_path / "machine.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(machine, "CONFIG", path)
    return path


@pytest.fixture(autouse=True)
def _fresh_cache():
    account._cache.clear()
    yield
    account._cache.clear()


# ---------- the account email ----------

def test_email_is_read_from_claude_json_only_that_field(tmp_path):
    home = _home(tmp_path)
    assert account.claude_account_email(home) == EMAIL


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"oauthAccount": null}', '{"oauthAccount": {"emailAddress": 5}}',
                                 '{"oauthAccount": {}}', '{"oauthAccount": {"emailAddress": "  "}}'])
def test_email_is_none_on_any_problem(tmp_path, raw):
    home = _home(tmp_path, raw=raw)
    assert account.claude_account_email(home) is None


def test_email_missing_file_or_folder_in_its_place(tmp_path):
    home = tmp_path / "nohome"
    home.mkdir()
    assert account.claude_account_email(home) is None
    (home / ".claude.json").mkdir()
    assert account.claude_account_email(home) is None


def test_default_home_is_the_user_home(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows: %USERPROFILE%\.claude.json
    assert account.claude_account_email() == EMAIL


# ---------- the gate ----------

def test_allowed_only_with_the_switch_on_and_the_account_in_the_list(tmp_path, monkeypatch):
    home = _home(tmp_path)
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[OTHER, EMAIL.upper()])
    assert account.generate_allowed(home=home) is True     # case-insensitive


@pytest.mark.parametrize("cfg", [
    {},                                                                         # no switch
    {"generate_for_me": False, "generate_for_me_accounts": [EMAIL]},            # switch off
    {"generate_for_me": "true", "generate_for_me_accounts": [EMAIL]},           # not a real true
    {"generate_for_me": 1, "generate_for_me_accounts": [EMAIL]},
    {"generate_for_me": True},                                                  # no list
    {"generate_for_me": True, "generate_for_me_accounts": []},
    {"generate_for_me": True, "generate_for_me_accounts": EMAIL},               # a string, not a list
    {"generate_for_me": True, "generate_for_me_accounts": [OTHER]},             # another account
    {"generate_for_me": True, "generate_for_me_accounts": [5, None]},
])
def test_fails_closed(tmp_path, monkeypatch, cfg):
    home = _home(tmp_path)
    _machine(tmp_path, monkeypatch, **cfg)
    assert account.generate_allowed(home=home) is False


def test_fails_closed_when_logged_out_or_machine_json_broken(tmp_path, monkeypatch):
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    assert account.generate_allowed(home=_home(tmp_path, raw="{}")) is False           # logged out
    broken = tmp_path / "broken.json"
    broken.write_text("{nope", encoding="utf-8")
    monkeypatch.setattr(machine, "CONFIG", broken)
    assert account.generate_allowed(home=_home(tmp_path)) is False
    monkeypatch.setattr(machine, "CONFIG", tmp_path / "missing.json")
    assert account.generate_allowed(home=_home(tmp_path)) is False


def test_a_new_login_is_seen_without_a_restart(tmp_path, monkeypatch):
    home = _home(tmp_path)
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    assert account.generate_allowed(home=home) is True
    import os
    import time
    (home / ".claude.json").write_text(json.dumps({"oauthAccount": {"emailAddress": OTHER, "x": "longer text"}}),
                                       encoding="utf-8")
    later = time.time() + 5
    os.utime(home / ".claude.json", (later, later))
    assert account.generate_allowed(home=home) is False


def test_the_email_is_never_logged(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path)
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    account.generate_allowed(home=home)
    account.generate_allowed(home=_home(tmp_path, email=OTHER))
    out = capsys.readouterr()
    assert EMAIL not in out.out + out.err and OTHER not in out.out + out.err


# ---------- the ElevenLabs key: only "set" / "not set" ----------

@pytest.mark.parametrize("raw,want", [
    (None, False), ("", False), ("nope", False), ("[]", False), ('{"elevenlabs_api_key": ""}', False),
    ('{"elevenlabs_api_key": "   "}', False), ('{"elevenlabs_api_key": 12}', False),
    ('{"elevenlabs_api_key": "sk_live_abc123"}', True),
])
def test_key_set_only_says_yes_or_no(tmp_path, raw, want):
    path = tmp_path / "secrets.json"
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
    assert account.elevenlabs_key_set(path) is want


def test_secrets_file_sits_next_to_machine_json():
    assert account.SECRETS == TOOLS.parent / "secrets.json"


# ---------- secrets.json is git-ignored; the example is tracked ----------

def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def test_secrets_json_is_git_ignored():
    if _git("rev-parse", "--is-inside-work-tree").returncode:
        pytest.skip("not a git checkout")
    assert _git("check-ignore", "-q", ".claude/edit-mo-to/secrets.json").returncode == 0
    assert _git("check-ignore", "-q", ".claude/edit-mo-to/machine.json").returncode == 0
    assert _git("check-ignore", "-q", ".claude/edit-mo-to/secrets.example.json").returncode == 1   # tracked example


def test_secrets_example_holds_only_a_placeholder():
    ex = json.loads((TOOLS.parent / "secrets.example.json").read_text(encoding="utf-8"))
    assert ex["elevenlabs_api_key"] == ""
    assert account.elevenlabs_key_set(TOOLS.parent / "secrets.example.json") is False


def test_machine_example_lists_the_switch_without_real_emails():
    ex = json.loads((TOOLS.parent / "machine.example.json").read_text(encoding="utf-8"))
    opt = ex["_optional"]
    assert "generate_for_me" in opt and "generate_for_me_accounts" in opt
    text = json.dumps(ex)
    assert "@" not in text.replace("<you>@", "")  # placeholder only, never a real address
    assert "generate_for_me" not in ex and "generate_for_me_accounts" not in ex


def test_no_account_email_in_tracked_files():
    """The emails in this computer's machine.json (if any) appear in no tracked file. The test names none itself."""
    if _git("rev-parse", "--is-inside-work-tree").returncode:
        pytest.skip("not a git checkout")
    try:
        accounts = json.loads((TOOLS.parent / "machine.json").read_text(encoding="utf-8")).get("generate_for_me_accounts")
    except (OSError, ValueError, AttributeError):
        accounts = None
    if not isinstance(accounts, list) or not accounts:
        pytest.skip("no Generate for me accounts on this computer")
    for a in accounts:
        if isinstance(a, str) and a.strip():
            hits = _git("grep", "-l", "-i", "-F", a.strip(), "--", ".", ":!*.mp3").stdout
            assert hits == "", "an account email is in a tracked file"   # the email itself is never shown


def test_machine_py_print_hides_the_account_list(tmp_path):
    cfg = {"generate_for_me": True, "generate_for_me_accounts": [EMAIL]}
    shown = machine.printable({**machine.PATHS, **cfg})
    assert EMAIL not in json.dumps(shown)
    assert shown["generate_for_me"] is True and shown["generate_for_me_accounts"] == "(1 account, hidden)"


# ---------- prefs: the first-click warning, the voice and model ----------

def test_new_prefs_have_defaults_and_checks(tmp_path):
    p = js.read_prefs(tmp_path / "prefs.json")
    assert p["generate_warned_at"] is None and p["elevenlabs_voice"] is None and p["elevenlabs_model"] is None
    got = js.update_prefs(tmp_path, {"generate_warned_at": "2026-10-28T10:00:00+08:00",
                                     "elevenlabs_voice": "21m00Tcm4TlvDq8ikWAM", "elevenlabs_model": "eleven_multilingual_v2"})
    assert got["generate_warned_at"] == "2026-10-28T10:00:00+08:00"
    assert got["elevenlabs_voice"] == "21m00Tcm4TlvDq8ikWAM" and got["elevenlabs_model"] == "eleven_multilingual_v2"
    assert js.update_prefs(tmp_path, {"elevenlabs_voice": None})["elevenlabs_voice"] is None


@pytest.mark.parametrize("patch", [
    {"generate_warned_at": "yesterday"}, {"generate_warned_at": 5}, {"generate_warned_at": True},
    {"elevenlabs_voice": "../../etc"}, {"elevenlabs_voice": "a b"}, {"elevenlabs_voice": ""}, {"elevenlabs_voice": "x" * 65},
    {"elevenlabs_model": "Eleven Multi"}, {"elevenlabs_model": 3},
])
def test_bad_new_prefs_are_refused(tmp_path, patch):
    with pytest.raises(ValueError):
        js.update_prefs(tmp_path, patch)


# ---------- the server: /api/job "generate", /api/generate ----------

class _C:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"

    def json(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        h = {"X-EMT-Token": TOKEN, **({"Content-Type": "application/json"} if body is not None else {})}
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")


@pytest.fixture
def srv(tmp_path, monkeypatch):
    root, tmp = tmp_path / "root", tmp_path / "tmp"
    root.mkdir()
    tmp.mkdir()
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp))
    home = _home(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    secrets = tmp_path / "secrets.json"
    monkeypatch.setattr(account, "SECRETS", secrets)
    s = server.make_server(0, root, tmp, TOKEN)
    t = threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    folder = root / "Gen Job"
    folder.mkdir()
    js.save(folder, js.new_job(folder, "Client", "Product"))
    yield _C(s.server_address[1]), folder, secrets
    s.shutdown()
    s.server_close()


def _job(c, folder):
    status, text = c.json("GET", "/api/job?" + urllib.parse.urlencode({"folder": folder.as_posix()}))
    assert status == 200, text
    return json.loads(text), text


def test_job_says_generate_true_only_for_the_owner(srv, tmp_path, monkeypatch):
    c, folder, _ = srv
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    data, text = _job(c, folder)
    assert data["generate"] is True
    assert EMAIL not in text and "emailAddress" not in text and "generate_for_me_accounts" not in text


def test_job_says_generate_false_otherwise(srv, tmp_path, monkeypatch):
    c, folder, _ = srv
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[OTHER])
    data, text = _job(c, folder)
    assert data["generate"] is False and OTHER not in text and EMAIL not in text
    assert "clip_files" not in data
    _machine(tmp_path, monkeypatch, generate_for_me=False, generate_for_me_accounts=[EMAIL])
    assert _job(c, folder)[0]["generate"] is False


def test_job_lists_clip_files_for_the_owner(srv, tmp_path, monkeypatch):
    c, folder, _ = srv
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    (folder / "clips").mkdir()
    (folder / "clips" / "V01_L02.mp4").write_bytes(b"x")
    (folder / "clips" / ".hidden.mp4").write_bytes(b"x")
    (folder / "clips" / "notes.txt").write_text("x", encoding="utf-8")
    data, _ = _job(c, folder)
    assert data["clip_files"] == ["V01_L02.mp4"]


def test_job_sends_the_mtimes_of_clips_and_voice_files(srv, tmp_path, monkeypatch):
    """Final review 2, M-11: the "Clip in folder" / "Voiceover in vo/" chips compare a file's time with the Generate
    click, so the page gets each file's mtime (ns, like keyframe_mtimes)."""
    import os
    c, folder, _ = srv
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    (folder / "clips").mkdir()
    (folder / "clips" / "V01_L02.mp4").write_bytes(b"x")
    os.utime(folder / "clips" / "V01_L02.mp4", ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    (folder / "vo").mkdir()
    (folder / "vo" / "vo_full.mp3").write_bytes(b"id3")
    os.utime(folder / "vo" / "vo_full.mp3", ns=(1_700_000_100_000_000_000, 1_700_000_100_000_000_000))
    data, _ = _job(c, folder)
    assert data["clip_mtimes"] == {"V01_L02.mp4": 1_700_000_000_000_000_000}
    assert data["vo_mtimes"] == {(folder / "vo" / "vo_full.mp3").resolve().as_posix(): 1_700_000_100_000_000_000}


def test_generate_route_shows_key_state_never_the_key(srv, tmp_path, monkeypatch):
    c, folder, secrets = srv
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    status, text = c.json("GET", "/api/generate")
    assert status == 200 and json.loads(text) == {"allowed": True, "elevenlabs_key": False}
    secrets.write_text(json.dumps({"elevenlabs_api_key": "sk_very_secret_value"}), encoding="utf-8")
    status, text = c.json("GET", "/api/generate")
    assert json.loads(text) == {"allowed": True, "elevenlabs_key": True}
    assert "sk_very_secret_value" not in text
    for path in ("/api/prefs", "/api/settings", "/api/checks", "/api/generators"):
        assert "sk_very_secret_value" not in c.json("GET", path)[1], path
    assert "sk_very_secret_value" not in _job(c, folder)[1]


def test_generate_route_for_anyone_else_says_only_no(srv, tmp_path, monkeypatch):
    c, _, secrets = srv
    secrets.write_text(json.dumps({"elevenlabs_api_key": "sk_x"}), encoding="utf-8")
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[OTHER])
    status, text = c.json("GET", "/api/generate")
    assert status == 200 and json.loads(text) == {"allowed": False}


def test_settings_never_shows_the_account_list(srv, tmp_path, monkeypatch):
    c, _, _ = srv
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    status, text = c.json("GET", "/api/settings")
    assert status == 200 and EMAIL not in text and "generate_for_me" not in text


def test_settings_save_keeps_the_switch_and_list(srv, tmp_path, monkeypatch):
    c, _, _ = srv
    cfg = _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    status, text = c.json("POST", "/api/settings", {"gui_port": 4811})
    assert status == 200, text
    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved["generate_for_me"] is True and saved["generate_for_me_accounts"] == [EMAIL]
    assert EMAIL not in text


def test_generate_click_is_an_action_event(srv, tmp_path, monkeypatch):
    c, folder, _ = srv
    _machine(tmp_path, monkeypatch, generate_for_me=True, generate_for_me_accounts=[EMAIL])
    status, text = c.json("POST", "/api/inbox", {"folder": folder.as_posix(), "event": {
        "type": "action", "step": "storyboard", "target": "generate:storyboard:SB-1"}})
    assert status == 200, text
    data, _ = _job(c, folder)
    assert [e["target"] for e in data["pending"]] == ["generate:storyboard:SB-1"]


# ---------- job.py can-generate ----------

def _can(tmp_path, monkeypatch, capsys, home, cfg):
    import job
    _machine(tmp_path, monkeypatch, **cfg)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    account._cache.clear()
    job.main(["can-generate"])
    out = capsys.readouterr()
    return 0, out.out, out.err


def test_can_generate_prints_allowed(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path)
    code, out, err = _can(tmp_path, monkeypatch, capsys, home, {"generate_for_me": True, "generate_for_me_accounts": [EMAIL]})
    assert code == 0 and json.loads(out) == {"ok": True, "allowed": True}
    assert EMAIL not in out + err


def test_can_generate_fails_closed(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path)
    for cfg in ({}, {"generate_for_me": True, "generate_for_me_accounts": [OTHER]},
                {"generate_for_me": False, "generate_for_me_accounts": [EMAIL]}):
        code, out, err = _can(tmp_path, monkeypatch, capsys, home, cfg)
        assert code == 0 and json.loads(out) == {"ok": True, "allowed": False}, cfg
        assert EMAIL not in out + err and OTHER not in out + err


# ---------- Task G fix: the shared isolation (conftest.py) is active for GUI tests ----------

def test_gui_tests_never_see_the_real_home_or_machine_json():
    from conftest import REAL_CONFIG, REAL_HOME
    assert Path.home().resolve() != REAL_HOME
    assert Path(machine.CONFIG).resolve() != REAL_CONFIG
    with pytest.raises(AssertionError):
        account._home(REAL_HOME)            # reading the real ~/.claude.json would fail the test
    assert account.generate_allowed() is False
