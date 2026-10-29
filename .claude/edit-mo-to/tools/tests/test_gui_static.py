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


def _x(text):
    """A file's text plus the English words of every word key it uses (Task B2 moved the app's words to words.js),
    so a check for a visible phrase still finds it."""
    import json as j
    import re as r
    raw = (STATIC / "words.js").read_text(encoding="utf-8")
    en = j.loads(raw.split("/* WORDS-START */", 1)[1].split("/* WORDS-END */", 1)[0].strip()
                 .removeprefix("export const WORDS =").strip().removesuffix(";"))["en"]
    extra = [en[g][k] for g, k in r.findall(r'["`]([a-z_]+)\.([a-z_]+)["`]', text) if g in en and k in en[g]]
    return text + "\n" + "\n".join(extra)


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
    app = _x((STATIC / "app.js").read_text(encoding="utf-8") + (STATIC / "index.html").read_text(encoding="utf-8"))
    for needle in ("#/settings", "/api/job", "If-None-Match", "1500", "This page is coming",
                   "Claude is listening", "Claude isn't listening. Your message is saved; it's picked up when "
                   "Claude next checks, or type 'go' in chat. If Claude asked for permission, answer it in chat.",
                   "Tell Claude anything"):
        assert needle in app, needle
    ui = _x((STATIC / "ui.js").read_text(encoding="utf-8"))
    for name in ("chip", "gateBar", "askBox", "table", "dropZone", "copyButton", "pendingChip", "dialog"):
        assert f"export function {name}(" in ui, name
    assert "Sent · waiting for Claude" in ui
    assert "Tell Claude about this step" in ui
    settings = _x((STATIC / "pages" / "settings.js").read_text(encoding="utf-8"))
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
    brief = _x((STATIC / "pages" / "brief.js").read_text(encoding="utf-8"))
    assert "Additional instructions" in brief
    assert "Specific Instructions".lower() not in brief.lower()


def test_dialogs_cover_the_spec_list():
    text = _x((STATIC / "dialogs.js").read_text(encoding="utf-8"))
    assert "export function open(" in text and "/api/new" in text
    for name in ("new", "capcut", "name", "contact", "oldvo", "inplace", "learn"):
        assert f'{name}:' in text or f'"{name}"' in text, name
    for needle in ("I quit it, check again", "Cancel this change", "Use anyway", "Mark for regenerate", "Copy prompt"):
        assert needle in text, needle
    assert ".innerHTML" not in text and "html:" not in text  # data reaches the DOM as text only


def test_carry_overs_in_shell():
    ui = _x((STATIC / "ui.js").read_text(encoding="utf-8"))
    assert "That question closed; Claude asked something new" in ui
    assert "upload_kind" not in ui and "upload_id" not in ui
    dash = (STATIC / "pages" / "dashboard.js").read_text(encoding="utf-8")
    assert "etag" in dash and "#" not in "".join(l for l in dash.splitlines() if "gradient" in l)
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    copied = next(l for l in css.splitlines() if l.startswith(".btn.copied"))
    assert "#" not in copied
    app = _x((STATIC / "app.js").read_text(encoding="utf-8"))
    assert "Open now" in app and "Waits for: " in app


def test_storyboard_js_has_approve_all_and_copy():
    text = _x((STATIC / "pages" / "storyboard.js").read_text(encoding="utf-8"))
    for needle in ("Approve all", "Approve anyway", "Wait for images", "Copy prompt", "prompt comes after the character sheet",
                   "Open share page", 'dropZone("keyframe"', '"shot"', '"need"', "storyboard.f_${key}"):
        assert needle in text, needle
    assert _words()["storyboard"]["f_need"] == "Needs image"
    assert ".innerHTML" not in text and "html:" not in text  # storyboard.json reaches the DOM as text only
    # the approval question leaves the gate bar only when Approve all is drawn (board read, step body shown)
    assert "hide: q && approveAllDrawn(data) ? [q.id] : []" in text
    assert 'approveAllDrawn = (data) => Boolean(data?.storyboard) && stateOf(data, STEP) !== "pending"' in text
    dialogs = _x((STATIC / "dialogs.js").read_text(encoding="utf-8"))
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
    assert "SB-${i + 1}" in (STATIC / "board.js").read_text(encoding="utf-8")  # a beat without an id keeps its card
    assert "keyframe_mtimes" in text  # the image cache-buster is the file's mtime
    assert "approvedEv" not in text  # "approved" only from beat.status
    assert '"storyboard.st_sent"' in text and "approval sent" in _x(text)
    assert '"character_sheet"' in text and "It's saved" in _x(text)


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
    assert "Could not check: delete TEMP_EN_delete_me before export if present" in _x(text)


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


def _all_words():
    text = (STATIC / "words.js").read_text(encoding="utf-8")
    body = text.split("/* WORDS-START */", 1)[1].split("/* WORDS-END */", 1)[0]
    body = body.strip().removeprefix("export const WORDS =").strip().removesuffix(";")
    return _json.loads(body)


def _words():
    """The English word list (WORDS.en)."""
    return _all_words()["en"]


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
    key = _re.compile(r'["`](' + "|".join(sorted(w)) + r')\.([a-z_]+)["`]')
    used = set()
    for p in _js_files():
        if p.name == "words.js":
            continue
        for g, k in key.findall(p.read_text(encoding="utf-8")):
            used.add(f"{g}.{k}")
    assert len(used) > 250, len(used)
    missing = sorted(k for k in used if not _has(_words(), k))
    assert not missing, missing
    no_tl = sorted(k for k in used if not _is_label(k) and not _has(_all_words()["tl"], k))
    assert not no_tl, no_tl


def test_every_step_has_a_title_a_why_line_and_a_time_guess():
    w = _words()
    for s in STEP_PAGES:
        assert _has(w, f"step.{s}") and _has(w, f"why.{s}") and _has(w, f"time.{s}"), s
        assert w["time"][s].startswith("About "), s
    for k in HELP_KEYS:
        assert _has(w, f"help.{k}") and _has(w, f"word.{k}"), k
    assert "2 seconds and 12 frames" in w["help"]["time"] and "30 frames = 1 second" in w["help"]["fps"]
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


def test_strip_and_board_share_one_rule():
    """The strip names only pictures that can be made now (a prompt is written; character sheets first), using the
    same board helpers as the storyboard page and the shot dialog; it asks for a voiceover only when vo/ is empty."""
    board = (STATIC / "board.js").read_text(encoding="utf-8")
    for name in ("export function boardItems(", "export const isClient", "export const promptOf", "export const needsImage",
                 "export function picturesToMake("):
        assert name in board, name
    assert "promptOf(it)" in board[board.index("export function picturesToMake("):]
    for page in (_page("storyboard.js"), (STATIC / "dialogs.js").read_text(encoding="utf-8")):
        assert 'from "../board.js"' in page or 'from "./board.js"' in page
        assert "export function boardItems(" not in page and "const needsImage =" not in page
    nxt = (STATIC / "nextstep.js").read_text(encoding="utf-8")
    assert "picturesToMake(data)" in nxt and "data?.vo" in nxt and 'e.type === "upload" && e.step === "voiceover"' not in nxt
    words = (STATIC / "words.js").read_text(encoding="utf-8")
    assert "LIST_MAX = 4" in words and _has(_words(), "label.more")


def test_prompts_page_asks_the_model_for_any_site_with_models():
    """Task H2: the model question follows the site's own `models` (Google Flow too), never a named site."""
    text = _page("prompts.js")
    assert "row?.models" in text and "data.generators" in text
    assert "=== \"higgsfield\"" not in text and "=== 'higgsfield'" not in text
    assert "row.label" in text            # the question group reads "<site> model" from the table
    assert "ignore: stale" in text        # a model answered for the other site does not carry over when the site changes


# --- Task B2: every app word in English and Taglish, the language switch, Start practice ---

def _flat(d, pre=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, f"{pre}{k}."))
        else:
            out[f"{pre}{k}"] = v
    return out


def _is_label(key):
    group, name = key.split(".", 1)
    spec = _all_words()["labels"].get(group)
    return spec == "*" or (isinstance(spec, list) and name in spec)


def test_sentences_have_taglish_and_labels_stay_english():
    """Spec "Beginner friendly", Language: labels (buttons, tabs, filters, step names, chips, field and column names,
    section titles, menu items) have one English line for both languages; every sentence has a Taglish line. A missing
    `tl` sentence fails here, so the shipped app never falls back to English for one."""
    w = _all_words()
    assert set(w) == {"labels", "en", "tl"}
    en, tl = _flat(w["en"]), _flat(w["tl"])
    for group, spec in w["labels"].items():
        assert group in w["en"], group
        if spec != "*":
            assert all(k in w["en"][group] for k in spec), group
    labels = sorted(k for k in en if _is_label(k))
    sentences = sorted(k for k in en if not _is_label(k))
    assert len(labels) > 150 and len(sentences) > 200, (len(labels), len(sentences))
    assert sorted(k for k in labels if k in tl) == [], "a label has a separate tl value"
    assert sorted(k for k in sentences if k not in tl) == [], "a sentence has no tl value"
    assert sorted(set(tl) - set(en)) == [], "only in tl"
    for k in sentences:
        assert isinstance(tl[k], str) and tl[k].strip(), k
        assert sorted(_re.findall(r"\{(\w+)\}", en[k])) == sorted(_re.findall(r"\{(\w+)\}", tl[k])), k
    differs = sum(en[k] != tl[k] for k in sentences)
    assert differs / len(sentences) > 0.85, f"only {differs} of {len(sentences)} sentences differ"
    for k in ("common.send", "storyboard.approve_all", "storyboard.copy_prompt", "storyboard.share", "storyboard.f_all",
              "storyboard.f_need", "storyboard.f_changed", "state.waiting", "tag.open", "storyboard.st_image",
              "shell.settings", "step.timing", "tag.you", "card.not_yet", "card.temp_on", "app.waits_for"):
        assert _is_label(k), k     # Joshua's examples: English in Taglish mode too
    for k in ("now.working", "now.pictures", "why.storyboard", "help.temp_en", "sp.not_listening", "app.listening_off",
              "common.not_sent", "practice.no_claude", "practice.mac_automation"):
        assert k in tl, k          # sentences: Taglish
    assert tl["now.working"].endswith("Wala ka pang gagawin.")
    for k in sentences:            # a sentence that names a button names it as the button reads: in English
        for button in ("CapCut is closed", "Check clips", "Start practice"):
            if button in en[k]:
                assert button in tl[k], (k, button)


def test_t_picks_the_language_and_falls_back_to_english():
    text = (STATIC / "words.js").read_text(encoding="utf-8")
    for needle in ("export function setLang(", "export const getLang", "WORDS[lang]", "WORDS.en", "export function tEn(",
                   "export function parts("):
        assert needle in text, needle
    assert "(30 frames = 1 second)" not in text.split("/* WORDS-END */", 1)[1]  # the fps note is a word too


def test_prompts_for_video_sites_and_brand_never_translated():
    tl = _flat(_all_words()["tl"])
    joined = " ".join(tl.values())
    for keep in ("Higgsfield", "CapCut", "TEMP_EN"):
        assert keep in joined, keep
    idx = (STATIC / "index.html").read_text(encoding="utf-8")
    for brand in (">JC<", ">Edit Mo To<", "by Joshua Calonge", "Deuteronomy 8:18", VERSE):
        assert brand in idx, brand
    for line in idx.splitlines():   # branding and the verse carry no word key, so they never change
        if any(b in line for b in ("by Joshua Calonge", "Deuteronomy", "Remember the Lord", ">JC<")):
            assert "data-w" not in line, line


def test_index_html_words_have_keys():
    idx = (STATIC / "index.html").read_text(encoding="utf-8")
    keys = _re.findall(r'data-w(?:-label|-ph)?="([a-z_]+\.[a-z_]+)"', idx)
    assert len(keys) >= 15, keys
    for k in keys:
        assert _has(_words(), k) and (_is_label(k) or _has(_all_words()["tl"], k)), k
    body = idx[idx.index("<body>"):]
    body = _re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body, flags=_re.S)
    for m in _re.finditer(r">([^<>]*[A-Za-z][^<>]*)<", body):
        text = m.group(1).strip()
        if not text or text in ("JC", "Edit Mo To", "by Joshua Calonge", "Claude", "Deuteronomy 8:18") or "Remember the Lord" in text:
            continue
        before = body[:m.start() + 1]
        tag = before[before.rindex("<"):]
        assert "data-w=" in tag, f"index.html text without a word key: {text!r}"
    for attr in ("aria-label", "placeholder"):
        for m in _re.finditer(attr + r'="([^"]+)"', body):
            if m.group(1) == "Edit Mo To":
                continue
            tag = body[body.rindex("<", 0, m.start()):body.index(">", m.start())]
            assert ("data-w-label" if attr == "aria-label" else "data-w-ph") in tag, m.group(0)


# string literals that are not words for the editor: CSS classes, routes, ids, event names, key names, formats ...
NOT_WORDS = {"Enter", "Escape", "ArrowLeft", "ArrowRight", "Notification", "Content-Type", "If-None-Match",
             "X-EMT-Token", "ETag", "INPUT", "TEXTAREA", "SELECT", "PUT", "POST", "GET", "Edit Mo To", "TEMP_EN",
             "JC", "PASS", "FLAG", "OK", "Copy"}


def _literals(code):
    """The string literals of JS code (comments removed): "..." and '...' as is, `...` with ${...} parts removed."""
    code = _re.sub(r"/\*.*?\*/", "", code, flags=_re.S)
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if c == "/" and code[i + 1:i + 2] == "/":
            i = code.find("\n", i)
            i = n if i < 0 else i
            continue
        if c == "/" and _re.search(r"(^|[(,=:\[!&|?{};]|return)\s*$", code[max(0, i - 12):i]):  # a regex literal
            j, cls = i + 1, False
            while j < n and (code[j] != "/" or cls):
                if code[j] == "\\":
                    j += 1
                elif code[j] == "[":
                    cls = True
                elif code[j] == "]":
                    cls = False
                j += 1
            i = j + 1
            continue
        if c in "\"'`":
            j, buf, depth = i + 1, [], 0
            while j < n and not (code[j] == c and depth == 0):
                if code[j] == "\\":
                    buf.append(code[j:j + 2])
                    j += 2
                    continue
                if c == "`" and code[j:j + 2] == "${":
                    depth += 1
                    j += 2
                    continue
                if depth and code[j] == "}":
                    depth -= 1
                    j += 1
                    continue
                if not depth:
                    buf.append(code[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
            continue
        i += 1
    return out


def _wordy(s):
    """A literal that reads as words for the editor: a capitalised word, or two words, or a sentence."""
    s = s.strip()
    if not s or s in NOT_WORDS or _re.fullmatch(r"[a-z_]+(\.[a-z_]+)+", s):          # a word key
        return False
    if not _re.search(r"[A-Za-z]", s) or _re.fullmatch(r"\d+ [KMG]iB", s) or s.endswith("· Edit Mo To"):
        return False                                                                  # "?", sizes, the brand
    if _re.search(r"[/<>=#{};()]|^\.|^-|https?:|\.(js|json|png|html|css)$", s):     # routes, selectors, markup, files
        return False
    if _re.fullmatch(r"[a-z0-9_:\-]+( [a-z0-9_:\-]+)*", s) and " " in s and not s.endswith((".", "?", "…")):
        return False                                                                  # CSS class lists: "btn sm pri"
    return bool(_re.search(r"\b[A-Z][a-z]+", s) or _re.search(r"[a-z]+ [a-z]+", s) or s.endswith(("…", "?")))


LITERAL_ALLOWED = {  # (file, literal): not the app's own words
    ("app.js", "emt-k"), ("nextstep.js", "emt-notify-asked"),
}


def test_no_user_facing_literals_left_in_page_builders():
    """Every word the editor reads comes from words.js through t(); literals left are classes, routes, ids, codes."""
    bad = []
    for p in _js_files():
        if p.name == "words.js":
            continue
        for lit in _literals(p.read_text(encoding="utf-8")):
            if _wordy(lit) and (p.name, lit) not in LITERAL_ALLOWED:
                bad.append(f"{p.name}: {lit!r}")
    assert not bad, "\n".join(bad)


def test_language_switch_in_settings_and_auto():
    settings = _page("settings.js")
    for needle in ('"ui_lang"', '"auto"', '"en"', '"tl"', "settings.lang_h", 'role: "radio"', "savePrefs("):
        assert needle in settings, needle
    nxt = (STATIC / "nextstep.js").read_text(encoding="utf-8")
    assert "ui_lang_detected" in nxt and 'ui_lang === "auto"' in nxt and "setLang(" in nxt
    assert "export function onLangChange(" in nxt
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "onLangChange(" in app and "applyStaticWords" in app      # a change re-renders at once, no reload
    assert "loadPrefs(api)" in app[app.index("async function refreshCurrent"):app.index("function setFolder")]


def test_start_practice_button_and_copy_fallback():
    dash = _page("dashboard.js")
    assert '"/api/practice"' in dash and "practice.start" in dash
    for reason in ("no-claude", "failed", "unsupported", "busy"):
        assert f'"{reason}"' in dash, reason
    assert "copyButton(PRACTICE" in dash
    assert 'reply.hint === "automation"' in dash and "practice.mac_automation" in dash  # where to allow Terminal on a Mac
    fallback = dash[dash.index("const FALLBACK"):].split("\n", 1)[0]
    assert '"busy"' not in fallback and all(r in fallback for r in ('"no-claude"', '"failed"', '"unsupported"'))
    w = _words()["practice"]
    assert w["no_claude"] == ("Claude isn't installed as a terminal command on this computer. "
                              "Copy this and paste it into Claude instead.")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_t_switches_language_in_node():
    """t() answers in the language setLang picked, falls back to English for a key Taglish lacks, never blank."""
    script = """
import { WORDS, t, tEn, setLang, getLang, timeTitle, listText } from "%s";
const out = {};
out.en = t("now.working", { step: "Storyboard" });
out.changed = setLang("tl"); out.again = setLang("tl"); out.lang = getLang();
out.tl = t("now.working", { step: "Storyboard" });
out.tEn = tEn("practice.start");
out.label_tl = ["common.send", "storyboard.approve_all", "state.waiting", "step.timing"].map((k) => t(k));
delete WORDS.tl.practice.start; out.fallback = t("practice.start");
out.unknown = t("no.such_key");
out.time = timeTitle("0:00–2:12");
out.list = listText(["Shot 1", "Shot 2"]);
setLang("tagalog"); out.other = getLang();
console.log(JSON.stringify(out));
""" % (STATIC / "words.js").as_uri()
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = _json.loads(r.stdout)
    assert out["en"] == "Claude is working on Storyboard. Nothing to do yet."
    assert out["changed"] is True and out["again"] is False and out["lang"] == "tl"
    assert out["tl"] == "Si Claude ang gumagawa ng Storyboard. Wala ka pang gagawin."
    assert out["label_tl"] == ["Send", "Approve all", "Waiting on you", "Timing & cleanup"]  # labels stay English
    assert out["tEn"] == "Start practice" and out["fallback"] == "Start practice" and out["unknown"] == "no.such_key"
    assert out["time"] == "0 segundo at 0 frames hanggang 2 segundo at 12 frames (30 frames = 1 segundo)"
    assert out["list"] == "Shot 1 at Shot 2"
    assert out["other"] == "en"   # only "tl" turns Taglish on; Claude maps Tagalog to tl before it gets here


# --- Task H3: models Claude avoids, Claude's default model, Got flagged ---

MODEL_NAMES = ("Seedance", "seedance", "Kling", "kling", "Veo", "veo-", "Omni", "omni", "Google Flow", "google-flow",
               "Higgsfield")


def test_no_hard_coded_model_names_in_pages():
    """Model and site names come from generators.json (spec anti-goal: no second copy of the rules)."""
    for f in ("pages/prompts.js", "pages/settings.js", "pages/storyboard.js", "dialogs.js", "steppage.js", "nextstep.js"):
        text = (STATIC / f).read_text(encoding="utf-8")
        for literal in MODEL_NAMES:
            assert literal not in text, (f, literal)


def test_settings_has_the_avoid_list_and_claudes_default():
    text = _page("settings.js")
    assert '"/api/generators"' in text and "avoid_models" in text and "default_model" in text
    assert 'type: "checkbox"' in text and '"select"' in text
    en = _words()
    assert en["settings"]["avoid"] == "When Claude picks, never use"
    assert en["settings"]["default_model"] == "Claude's default model"
    for k in ("settings.models_h", "settings.avoid", "settings.default_model", "settings.no_default"):
        assert _is_label(k), k
    tl = _all_words()["tl"]
    for k in ("models_p", "default_hint"):
        assert k in tl["settings"], k
    n = (STATIC / "nextstep.js").read_text(encoding="utf-8")
    assert "avoid_models: []" in n and "default_model: null" in n


def test_model_question_highlights_claudes_default():
    text = _page("prompts.js")
    assert "picks" in text and "suggested" in text
    sp = (STATIC / "steppage.js").read_text(encoding="utf-8")
    assert "opts.suggested" in sp
    assert "prompts.default_hint" in text and "prompts" in _all_words()["tl"] and "default_hint" in _all_words()["tl"]["prompts"]


def test_got_flagged_on_prompt_rows_cards_and_the_shot_dialog():
    sp = (STATIC / "steppage.js").read_text(encoding="utf-8")
    assert "export function flaggedBox(" in sp and ":flagged`" in sp and 'type: "action"' in sp
    assert "pendingFor(data, target)" in sp and "pendingChip()" in sp
    assert "flaggedBox(" in _page("prompts.js") and "flaggedBox(" in _page("storyboard.js")
    assert "flaggedBox(" in (STATIC / "dialogs.js").read_text(encoding="utf-8")
    en, tl = _words(), _all_words()["tl"]
    assert en["flag"]["button"] == "Got flagged"
    assert en["flag"]["note_label"] == "What did the site say? (optional)"
    assert _is_label("flag.button") and _is_label("flag.note_label")
    assert "blocked this prompt" in en["flag"]["p"] and tl["flag"]["p"] != en["flag"]["p"]


# --- Task G: "Generate for me" (Joshua only; spec "Generate for me (Joshua only, 2026-10-28)") ---

GEN_WARN = ("Claude will use your own Chrome and your Google Flow credits. Google's terms may not allow automated use, "
            "so this could flag your account. Continue?")


def test_generate_buttons_only_when_the_server_says_so():
    sp = (STATIC / "steppage.js").read_text(encoding="utf-8")
    assert "export function generateButton(" in sp
    assert "data?.generate !== true" in sp                    # hidden unless /api/job says true (fail closed)
    assert "`generate:${step}:${id}`" in sp and 'type: "action"' in sp
    assert "generate_warned_at" in sp and "savePrefs(" in sp   # the first-click warning, asked once
    assert "pendingFor(data, target)" in sp
    sb, clips, vo = _page("storyboard.js"), _page("clips.js"), _page("voiceover.js")
    assert "generateButton(" in sb and '"gen.picture"' in sb
    assert "generatePicture(" in (STATIC / "dialogs.js").read_text(encoding="utf-8")   # the same button as the card
    assert "export const generatePicture" in sb
    assert "generateButton(" in clips and '"gen.clip"' in clips and "clip_files" in clips
    assert "generateButton(" in vo and '"gen.voiceover"' in vo and '"all"' in vo
    n = (STATIC / "nextstep.js").read_text(encoding="utf-8")
    assert "generate_warned_at: null" in n and "elevenlabs_voice: null" in n and "elevenlabs_model: null" in n


def test_generate_words_labels_english_sentences_taglish():
    en, tl = _words(), _all_words()["tl"]
    assert en["gen"]["picture"] == "Generate picture" and en["gen"]["clip"] == "Generate clip"
    assert en["gen"]["voiceover"] == "Generate voiceover"
    for k in ("gen.picture", "gen.clip", "gen.voiceover", "gen.continue", "gen.h", "gen.picture_saved", "gen.clip_saved",
              "gen.vo_saved", "settings.gen_h", "settings.el_key", "settings.key_set", "settings.key_not_set",
              "settings.el_voice", "settings.el_model"):
        assert _is_label(k), k
    assert en["gen"]["warn"] == GEN_WARN
    assert "ElevenLabs" in en["gen"]["vo_line"] and "account" not in en["gen"]["vo_line"]
    assert en["settings"]["key_where"] == ("Paste your key into .claude/edit-mo-to/secrets.json on this Mac. "
                                           "Never paste it in chat.")
    for k in ("warn", "vo_line", "p"):
        assert tl["gen"][k] and tl["gen"][k] != en["gen"][k], k
    for k in ("gen_p", "key_where", "voice_hint"):
        assert tl["settings"][k] and tl["settings"][k] != en["settings"][k], k


def test_settings_generate_card_shows_only_set_or_not_set():
    text = _page("settings.js")
    assert '"/api/generate"' in text and "elevenlabs_key" in text
    assert "allowed" in text and "elevenlabs_voice" in text and "elevenlabs_model" in text
    assert "settings.key_where" in text and "api_key" not in text and "secrets.json" not in text
    assert "generate_for_me_accounts" not in text and "email" not in text.lower()


def test_no_email_or_key_in_the_page_code():
    for p in _js_files():
        t = p.read_text(encoding="utf-8")
        assert "emailAddress" not in t and "xi-api-key" not in t and "elevenlabs_api_key" not in t, p.name


# --- Final review 2: M-8 (Generate clip only on the Generate-for-me site), M-11 (done chips compare times) ---

def test_generate_clip_only_for_the_generate_for_me_site():
    g = _json.loads((STATIC.parents[1] / "generators.json").read_text(encoding="utf-8"))
    on = [k for k, v in g["generators"].items() if v.get("generate_for_me") is True]
    assert on == ["google-flow"]                                  # the table says where Generate for me makes clips
    clips = _page("clips.js")
    assert "generate_for_me" in clips and "siteOf(" in clips and '"gen.clip_other_site"' in clips
    for literal in MODEL_NAMES:
        assert literal not in clips, literal                     # no second copy of the site list
    assert "export function siteOf(" in _page("prompts.js")
    en, tl = _words(), _all_words()["tl"]
    assert "{site}" in en["gen"]["clip_other_site"] and "{gen}" in en["gen"]["clip_other_site"]
    assert tl["gen"]["clip_other_site"] and "{site}" in tl["gen"]["clip_other_site"]


def test_done_chips_need_a_file_newer_than_the_generate_click():
    sp = (STATIC / "steppage.js").read_text(encoding="utf-8")
    assert "opts.doneAt" in sp and "asked && opts.done " not in sp and "Date.parse(" in sp
    sb, clips, vo = _page("storyboard.js"), _page("clips.js"), _page("voiceover.js")
    assert "doneAt:" in sb and "keyframe_mtimes" in sb
    assert "doneAt:" in clips and "clip_mtimes" in clips
    assert "doneAt:" in vo and "vo_mtimes" in vo


# --- Final review 2, M-3 (Settings part) ---

def test_settings_warns_about_a_damaged_prefs_file_and_turns_saving_off():
    text = _page("settings.js")
    assert "p.broken === true" in text or "p?.broken === true" in text
    assert "broken_path" in text and "broken_why" in text
    assert 'class: "banner err"' in text and 'role: "alert"' in text
    assert "settings.broken" in text
    en, tl = _words(), _all_words()["tl"]
    assert en["settings"]["broken"] == ("Your settings file is damaged, so nothing can be saved. Your \"never use\" "
                                        "models are still safe. Fix or delete {path}.")
    for k in ("broken", "broken_why", "broken_models"):
        assert not _is_label(f"settings.{k}"), k
        assert k in tl["settings"] and tl["settings"][k] != en["settings"][k], k
    # the path and reason come from the server: always as text nodes (parts / textContent), never through innerHTML
    assert "innerHTML" not in text and "html:" not in text
