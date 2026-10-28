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


STEP_PAGES = ["brief", "script", "storyboard", "voiceover", "timing", "prompts", "clips", "build", "review", "captions", "music",
              "export"]


def test_step_pages_and_dialogs_served(base):
    for rel in [*(f"pages/{p}.js" for p in STEP_PAGES), "dialogs.js", "pages.css"]:
        assert (STATIC / rel).is_file(), rel
        status, _, body = _get(f"{base}/static/{rel}")
        assert status == 200 and body == (STATIC / rel).read_bytes(), rel
    assert 'href="/static/pages.css"' in (STATIC / "index.html").read_text(encoding="utf-8")
    for p in STEP_PAGES:
        assert "export function render(" in (STATIC / "pages" / f"{p}.js").read_text(encoding="utf-8"), p


def test_brief_page_has_one_instructions_box():
    brief = (STATIC / "pages" / "brief.js").read_text(encoding="utf-8")
    assert "Additional instructions" in brief
    assert "Specific Instructions".lower() not in brief.lower()


def test_dialogs_cover_the_spec_list():
    text = (STATIC / "dialogs.js").read_text(encoding="utf-8")
    assert "export function open(" in text and "/api/new" in text
    for name in ("new", "capcut", "name", "contact", "oldvo", "inplace", "learn"):
        assert f'{name}:' in text or f'"{name}"' in text, name
    for needle in ("I quit it, check again", "Cancel this change", "Use anyway", "Mark for regenerate", "Copy prompt"):
        assert needle in text, needle
    assert ".innerHTML" not in text and "html:" not in text  # data reaches the DOM as text only


def test_carry_overs_in_shell():
    ui = (STATIC / "ui.js").read_text(encoding="utf-8")
    assert "That question closed; Claude asked something new" in ui
    assert "upload_kind" not in ui and "upload_id" not in ui
    dash = (STATIC / "pages" / "dashboard.js").read_text(encoding="utf-8")
    assert "etag" in dash and "#" not in "".join(l for l in dash.splitlines() if "gradient" in l)
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    copied = next(l for l in css.splitlines() if l.startswith(".btn.copied"))
    assert "#" not in copied
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "Open now" in app and "Waits for: " in app


def test_storyboard_js_has_approve_all_and_copy():
    text = (STATIC / "pages" / "storyboard.js").read_text(encoding="utf-8")
    for needle in ("Approve all", "Approve anyway", "Wait for images", "Copy prompt", "prompt comes after the character sheet",
                   "Open share page", "Needs image", 'dropZone("keyframe"', '"shot"'):
        assert needle in text, needle
    assert ".innerHTML" not in text and "html:" not in text  # storyboard.json reaches the DOM as text only
    # the approval question leaves the gate bar only when Approve all is drawn (board read, step body shown)
    assert "hide: q && approveAllDrawn(data) ? [q.id] : []" in text
    assert 'approveAllDrawn = (data) => Boolean(data?.storyboard) && stateOf(data, STEP) !== "pending"' in text
    dialogs = (STATIC / "dialogs.js").read_text(encoding="utf-8")
    for needle in ("function shot(", "learn, shot }", "Request change", "Approve shot", "Choose file"):
        assert needle in dialogs + text, needle
    if shutil.which("node"):
        r = subprocess.run(["node", "--check", str(STATIC / "pages" / "storyboard.js")], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


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
    assert job["card"]["generator"].startswith("Higgsfield · ")
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


def _page(name):
    return (STATIC / "pages" / name).read_text(encoding="utf-8")


def test_storyboard_final_review_fixes():
    text = _page("storyboard.js")
    assert "/approv/i" not in text  # the approval question is found by id only, never by its wording
    assert 'qs.find((q) => q.id === "approve") || null' in text
    assert "SB-${i + 1}" in text  # a beat without an id keeps its card
    assert "keyframe_mtimes" in text  # the image cache-buster is the file's mtime
    assert "approvedEv" not in text  # "approved" only from beat.status
    assert '"approval sent"' in text
    assert '"character_sheet"' in text and "It's saved" in text


def test_gate_duplicating_buttons_answer_the_gate():
    timing = _page("timing.js")
    assert 'gateAsks(data, "timing", "cuts")' in timing and 'answerGate(ctx, gate, "cuts"' in timing
    captions = _page("captions.js")
    assert 'gateAsks(data, "captions", "timelines")' in captions and 'answerGate(ctx, gate, "timelines"' in captions
    ui = (STATIC / "ui.js").read_text(encoding="utf-8")
    assert "q.yes" not in ui and "labels" in ui  # a page can relabel a confirm question's buttons


def test_export_always_checks_temp_en():
    text = _page("export.js")
    assert 'if (t === "removed" || t === "off"' not in text  # no skipped check
    assert "Could not check: delete TEMP_EN_delete_me before export if present" in text


def test_approval_sent_counts_only_unhandled_approves():
    """A handled approve (or one from an earlier round) never outranks "changed" or "comment open"."""
    text = _page("storyboard.js")
    body = text[text.index("export function statusOf"):text.index("export function shotText")]
    assert "!done.has(e.seq)" in body and 'e.type === "approve"' in body


def test_prompts_page_reads_the_generators_table():
    """The site and model choices come from generators.json via /api/job, never a list in the page (spec anti-goal)."""
    text = _page("prompts.js")
    assert "data.generators" in text or "data?.generators" in text
    for literal in ("Seedance", "seedance", "Kling", "kling", "Veo", "veo-", "Google Flow", "google-flow", "Higgsfield"):
        assert literal not in text, literal
    assert '"generator_model"' in text
    for name in _js_files():
        assert "Seedance" not in name.read_text(encoding="utf-8"), name.name


# --- Task B1: beginner friendly (words in one place, what to do now, word help, alerts, practice, no codes) ---
import json as _json  # noqa: E402
import re as _re  # noqa: E402

WORD_GROUPS = ("step", "why", "time", "help", "word", "label", "now", "alert", "settings", "practice", "page",
               "storyboard", "prompts")
HELP_KEYS = ("temp_en", "a_roll", "b_roll", "keyframe", "timeline", "vo", "character_sheet", "question", "time", "model",
             "prompt")


def _words():
    text = (STATIC / "words.js").read_text(encoding="utf-8")
    body = text.split("/* WORDS-START */", 1)[1].split("/* WORDS-END */", 1)[0]
    body = body.strip().removeprefix("export const WORDS =").strip().removesuffix(";")
    return _json.loads(body)


def _has(words, key):
    node = words
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, str) and node.strip() != ""


def test_words_js_served_and_parses(base):
    status, ctype, body = _get(base + "/static/words.js")
    assert status == 200 and "javascript" in ctype and body == (STATIC / "words.js").read_bytes()
    for rel in ("nextstep.js",):
        assert _get(f"{base}/static/{rel}")[0] == 200, rel
    w = _words()
    assert set(WORD_GROUPS) <= set(w)
    assert "export function t(" in (STATIC / "words.js").read_text(encoding="utf-8")
    assert "export function label(" in (STATIC / "words.js").read_text(encoding="utf-8")


def test_every_word_key_used_in_static_js_exists():
    w = _words()
    key = _re.compile(r'["`](' + "|".join(WORD_GROUPS) + r')\.([a-z_]+)["`]')
    used = set()
    for p in _js_files():
        if p.name == "words.js":
            continue
        for g, k in key.findall(p.read_text(encoding="utf-8")):
            used.add(f"{g}.{k}")
    assert len(used) > 40, sorted(used)
    missing = sorted(k for k in used if not _has(w, k))
    assert not missing, missing


def test_every_step_has_a_title_a_why_line_and_a_time_guess():
    w = _words()
    for s in STEP_PAGES:
        assert _has(w, f"step.{s}") and _has(w, f"why.{s}") and _has(w, f"time.{s}"), s
        assert w["time"][s].startswith("About "), s
    for k in HELP_KEYS:
        assert _has(w, f"help.{k}") and _has(w, f"word.{k}"), k
    assert "2 seconds and 12 frames" in w["help"]["time"] and "30 frames = 1 second" in w["help"]["time_value"]
    for group in ("why", "help"):  # plain words: no internal names
        text = " ".join(w[group].values()).lower()
        for name in ("plan_tools", "job.json", "gate", "generators.json", "sb-", "char-"):
            assert name not in text, (group, name)


def test_next_step_rules_are_data_with_words():
    text = (STATIC / "nextstep.js").read_text(encoding="utf-8")
    assert "export const RULES = [" in text and "export function nextStep(" in text
    keys = _re.findall(r'key: "(now\.[a-z_]+)"', text)
    for k in ("now.capcut", "now.pictures", "now.pictures_question", "now.voiceover", "now.question", "now.answered",
              "now.waiting", "now.working", "now.error", "now.done", "now.next"):
        assert k in keys, k
    w = _words()
    for k in keys + ["now.not_listening", "now.not_listening_ask", "now.error_card", "now.you", "now.claude", "now.none"]:
        assert _has(w, k), k
    assert "data.listening" in text            # "Claude isn't listening" only from the verified field
    assert "nowStrip(data" in (STATIC / "steppage.js").read_text(encoding="utf-8")
    assert "nowStrip(reply" in _page("dashboard.js")


def test_alerts_fire_on_a_new_question_only_and_ask_permission_on_a_click():
    text = (STATIC / "nextstep.js").read_text(encoding="utf-8")
    assert "export function watchQuestion(" in text and "watchQuestion(folder, data)" in (STATIC / "app.js").read_text(encoding="utf-8")
    body = text[text.index("export function watchQuestion("):]
    assert "!first && id && id !== before" in body   # not on first load, not on every poll
    arm = text[text.index("function arm()"):text.index("function softSound()")]
    assert 'addEventListener("click"' in arm and "requestPermission" in arm and "once: true" in arm
    assert text.count("requestPermission") == 1
    assert "AudioContext" in text and ".mp3" not in text and ".wav" not in text
    assert "titled(" in (STATIC / "app.js").read_text(encoding="utf-8")
    settings = _page("settings.js")
    assert 'role: "switch"' in settings and "savePrefs(" in settings
    assert '"/api/prefs"' in text


def test_practice_card_on_the_dashboard():
    dash = _page("dashboard.js")
    assert '"/practice-muna"' in dash and "copyButton(PRACTICE" in dash
    assert "practice.title" in dash and "practice.what" in dash


VISIBLE_CODE_ALLOWED = (  # where "SB-" / "CHAR-" may stay: ids, file names, regexes, comments
    'KEYFRAME_ID = /^(SB|CHAR)-\\d+$/;',
    "`SB-${i + 1}`",
    "[/^SB-(\\d+)$/i,",
    "/^CHAR-\\d+$/i.test(s)",
)


def test_no_codes_in_visible_text():
    for p in _js_files():
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//", 1)[0] if not line.lstrip().startswith(("//", "*", "/*")) else ""
            if "SB-" not in code and "CHAR-" not in code:
                continue
            assert any(a in code for a in VISIBLE_CODE_ALLOWED), f"{p.name}:{n}: {line.strip()}"
    sb, dlg = _page("storyboard.js"), (STATIC / "dialogs.js").read_text(encoding="utf-8")
    assert 'h("b", { class: "mono" }, it.id)' not in sb and "missing.join" in sb and "label(it.id, data)" in sb
    assert "${it.id} · " not in dlg and "storyboard.prev" in dlg
    prompts = _page("prompts.js")
    assert "label(r.id)" in prompts
    prompts = "\n".join(l for l in prompts.splitlines() if not l.lstrip().startswith(("//", "/*", "*")))
    for phrase in ("generators.json", "strictest limits in the table"):
        assert phrase not in prompts, phrase
    assert "tbl.safe" in prompts  # the safe numbers come from the data, not typed in


def test_word_help_buttons():
    ui = (STATIC / "ui.js").read_text(encoding="utf-8")
    tip = ui[ui.index("export function helpTip("):ui.index("export function timeText(")]
    for needle in ('"aria-describedby": id', 'role: "tooltip"', "help.${key}", 'type: "button"'):
        assert needle in tip, needle
    assert '"Escape"' in ui and "timeTitle(c)" in ui
    every = "".join(p.read_text(encoding="utf-8") for p in _js_files())
    used = set(_re.findall(r'helpTip\("([a-z_]+)"\)', every))
    used |= set(_re.findall(r'"([a-z_]+)"', every[every.index("const CARD_HELP"):].split("\n", 1)[0]))
    sb = _page("storyboard.js")
    used |= set(_re.findall(r'"([a-z_]+)"', sb[sb.index('t("help.row"), ...['):].split("]", 1)[0]))
    assert set(HELP_KEYS) - {"a_roll"} <= used, sorted(set(HELP_KEYS) - used)  # no page shows "A-roll" yet
