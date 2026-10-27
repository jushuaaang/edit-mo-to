"""Static front end of the companion GUI: files served, theme tokens, branding, JS syntax, demo job."""
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[2] / "gui"
STATIC = GUI / "static"
sys.path.insert(0, str(GUI))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jobstate as js  # noqa: E402
import server  # noqa: E402

TOKEN = "static-token-1"
TOKENS = ["--bg: #0C0B0A", "--panel: #151311", "--panel2: #1D1A17", "--line: #2A2622", "--line2: #3A342D",
          "--text: #F3EFE8", "--muted: #A69D91", "--dim: #6F675D", "--accent: #D4AF6A", "--on-accent: #1A1408",
          "--ok: #7DCB9C", "--wait: #93B5E3", "--err: #EE7B6E", "--opt: #BBA6E0"]
VERSE = "Remember the Lord your God, for it is he who gives you the ability to produce wealth."
OTHER_NAMES = ["Keytech"]


@pytest.fixture
def base(tmp_path):
    root, tmp = tmp_path / "root", tmp_path / "tmp"
    root.mkdir()
    tmp.mkdir()
    srv = server.make_server(0, root, tmp, TOKEN)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, "", e.read()


def _js_files():
    return sorted(STATIC.glob("*.js")) + sorted((STATIC / "pages").glob("*.js"))


def test_index_and_assets_served(base):
    status, ctype, body = _get(base + "/")
    assert status == 200 and "text/html" in ctype and b'type="module"' in body
    for rel in ("app.css", "app.js", "ui.js", "pages/dashboard.js", "pages/settings.js"):
        assert (STATIC / rel).is_file(), rel
    pages = sorted((STATIC / "pages").glob("*.js"))
    fonts = sorted((STATIC / "fonts").glob("*.woff2"))
    assert len(fonts) >= 3, "Space Grotesk, Inter and JetBrains Mono woff2"
    assert (STATIC / "fonts" / "OFL.txt").is_file()
    for p in [STATIC / "app.css", STATIC / "app.js", STATIC / "ui.js", *pages, *fonts]:
        rel = p.relative_to(STATIC).as_posix()
        status, ctype, body = _get(f"{base}/static/{rel}")
        assert status == 200, rel
        assert body == p.read_bytes(), rel
    assert _get(base + "/static/fonts/" + fonts[0].name)[1] == "font/woff2"


def test_css_has_obsidian_tokens():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    for token in TOKENS:
        assert token in css, token
    assert "prefers-reduced-motion" in css
    assert ":focus-visible" in css
    for family in ("Space Grotesk", "Inter", "JetBrains Mono"):
        assert f'font-family: "{family}"' in css, family
    assert "fonts.googleapis.com" not in css and "fonts.gstatic.com" not in css


def test_branding_and_verse():
    text = (STATIC / "index.html").read_text(encoding="utf-8") + (STATIC / "app.js").read_text(encoding="utf-8")
    assert ">JC<" in text
    assert "Edit Mo To" in text
    assert "by Joshua Calonge" in text
    assert VERSE.lower() in text.lower()
    assert "deuteronomy 8:18" in text.lower()
    everything = "".join(p.read_text(encoding="utf-8").lower()
                         for p in [STATIC / "index.html", STATIC / "app.css", *_js_files()])
    for name in OTHER_NAMES:
        assert name.lower() not in everything, name


def test_no_external_network_at_runtime():
    for p in [STATIC / "index.html", STATIC / "app.css", *_js_files()]:
        text = p.read_text(encoding="utf-8")
        for host in ("https://fonts.", "cdn.", "unpkg.com", "jsdelivr"):
            assert host not in text, f"{p.name}: {host}"


def test_shell_contract():
    app = (STATIC / "app.js").read_text(encoding="utf-8") + (STATIC / "index.html").read_text(encoding="utf-8")
    for needle in ("#/settings", "/api/job", "If-None-Match", "1500", "This page is coming",
                   "Claude is listening", "Claude isn't listening. Your message is saved; it's picked up when "
                   "Claude next checks, or type 'go' in chat. If Claude asked for permission, answer it in chat.",
                   "Tell Claude anything"):
        assert needle in app, needle
    ui = (STATIC / "ui.js").read_text(encoding="utf-8")
    for name in ("chip", "gateBar", "askBox", "table", "dropZone", "copyButton", "pendingChip", "dialog"):
        assert f"export function {name}(" in ui, name
    assert "Sent · waiting for Claude" in ui
    assert "Tell Claude about this step" in ui
    settings = (STATIC / "pages" / "settings.js").read_text(encoding="utf-8")
    for needle in ("Report a bug", "Suggest an improvement", "Send to Joshua", "/api/feedback", "issue_url"):
        assert needle in settings, needle


def test_job_reply_has_recent_events(tmp_path):
    """askBox shows a step's messages and gateBar knows an answer was sent: both read `events`."""
    import json
    root, tmp = tmp_path / "root", tmp_path / "tmp"
    folder = root / "Uvola Cereza Ácida"
    folder.mkdir(parents=True)
    tmp.mkdir()
    js.save(folder, js.new_job(folder, "Uvola", "Cereza"))
    for i in range(server.RECENT_EVENTS + 5):
        js.append_event(folder, {"type": "message", "step": "script", "text": f"m{i}"})
    srv = server.make_server(0, root, tmp, TOKEN)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    try:
        q = urllib.parse.quote(folder.as_posix())
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/job?folder={q}",
                                     headers={"X-EMT-Token": TOKEN})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read())
    finally:
        srv.shutdown()
        srv.server_close()
    assert len(body["events"]) == server.RECENT_EVENTS
    assert body["events"][-1]["text"] == f"m{server.RECENT_EVENTS + 4}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_js_syntax():
    files = _js_files()
    assert files
    for p in files:
        r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
        assert r.returncode == 0, f"{p.name}: {r.stderr}"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_demo_job(tmp_path, monkeypatch):
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp_path / "tmp"))
    import demo
    folder = tmp_path / "root" / "Uvola Cereza Ácida"
    demo.make(folder)
    job = js.load(folder)
    assert job["card"]["language"].lower().startswith("spanish")
    assert job["card"]["temp_en"] == "on"
    assert job["steps"]["storyboard"]["state"] == "waiting"
    assert job["gate"]["step"] == "storyboard"
    assert any(q["kind"] == "confirm" for q in job["gate"]["questions"])
    sb = __import__("json").loads((folder / "storyboard" / "storyboard.json").read_text(encoding="utf-8"))
    assert len(sb["beats"]) == 8 and len(sb["characters"]) == 1
    for name in ("SB-1", "SB-2", "SB-4", "SB-7", "CHAR-1"):
        assert (folder / "storyboard" / f"{name}.png").stat().st_size > 0, name
    assert not (folder / "storyboard" / "SB-5.png").exists()
    outputs = job["outputs"]
    assert any(outputs.get(s) for s in outputs)
    assert js.get_current() == folder.as_posix()
