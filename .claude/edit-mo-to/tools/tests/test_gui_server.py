import http.client
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[2] / "gui"
sys.path.insert(0, str(GUI))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jobstate as js  # noqa: E402
import machine  # noqa: E402
import server  # noqa: E402

TOKEN = "test-token-123"
DEMO = "Uvola Cereza Ácida"


class Client:
    def __init__(self, port, root, tmp):
        self.port, self.root, self.tmp = port, root, tmp
        self.base = f"http://127.0.0.1:{port}"

    def call(self, method, path, body=None, token=TOKEN, headers=None, raw=None):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode("utf-8"))
        h = dict(headers or {})
        if token:
            h["X-EMT-Token"] = token
        if body is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def json(self, method, path, body=None, **kw):
        status, headers, data = self.call(method, path, body, **kw)
        return status, (json.loads(data) if data else None)


@pytest.fixture
def api(tmp_path, monkeypatch):
    root, tmp = tmp_path / "root", tmp_path / "tmp"
    root.mkdir()
    tmp.mkdir()
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp))
    srv = server.make_server(0, root, tmp, TOKEN)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    yield Client(srv.server_address[1], root, tmp)
    srv.shutdown()
    srv.server_close()


def _demo(api):
    folder = api.root / DEMO
    folder.mkdir()
    js.save(folder, js.new_job(folder, "Uvola", "Cereza Ácida"))
    return folder


def _q(**kw):
    return "?" + urllib.parse.urlencode({k: str(v) for k, v in kw.items()})


def test_ping_needs_no_token(api):
    status, data = api.json("GET", "/api/ping", token=None)
    assert status == 200
    assert data == {"app": "edit-mo-to-gui", "version": server.API_VERSION, "pid": os.getpid(),
                    "config": server.fingerprint(api.root, api.tmp)}
    assert str(api.root) not in json.dumps(data) and str(api.tmp) not in json.dumps(data)  # paths stay private


def test_version_is_a_hash_of_the_gui_code(tmp_path):
    """Any change to gui/*.py or static/** gives a new version, so launch replaces a server running old code."""
    gui = tmp_path / "gui"
    (gui / "static" / "pages").mkdir(parents=True)
    (gui / "server.py").write_text("a", encoding="utf-8")
    (gui / "static" / "pages" / "x.js").write_text("b", encoding="utf-8")
    v1 = server.code_version(gui)
    assert isinstance(v1, str) and len(v1) >= 8
    (gui / "notes.txt").write_text("not code", encoding="utf-8")
    (gui / "__pycache__").mkdir()
    (gui / "__pycache__" / "server.cpython-312.pyc").write_bytes(b"x")
    assert server.code_version(gui) == v1
    (gui / "static" / "pages" / "x.js").write_text("c", encoding="utf-8")
    v2 = server.code_version(gui)
    assert v2 != v1
    (gui / "job.py").write_text("d", encoding="utf-8")
    assert server.code_version(gui) != v2
    assert server.API_VERSION == server.code_version(GUI)


def test_fingerprint_changes_with_root_and_tmp(tmp_path):
    a = server.fingerprint(tmp_path / "r1", tmp_path / "t")
    assert a == server.fingerprint(tmp_path / "r1", tmp_path / "t")
    assert a != server.fingerprint(tmp_path / "r2", tmp_path / "t")
    assert a != server.fingerprint(tmp_path / "r1", tmp_path / "t2")


def test_api_needs_token(api):
    assert api.json("GET", "/api/jobs", token=None)[0] == 401
    assert api.json("GET", "/api/jobs", token="wrong")[0] == 401
    assert api.json("GET", "/api/jobs")[0] == 200


def test_token_link_sets_cookie(api):
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
    conn.request("GET", f"/?k={TOKEN}")
    r = conn.getresponse()
    r.read()
    assert r.status == 302 and r.getheader("Location") == "/"
    cookie = r.getheader("Set-Cookie")
    assert f"emt={TOKEN}" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    conn.request("GET", "/api/jobs", headers={"Cookie": f"emt={TOKEN}"})
    r = conn.getresponse()
    r.read()
    assert r.status == 200
    conn.close()


def _raw(api, method, path, headers=None):
    """One request with http.client, so the path is sent exactly as written (no client-side normalising)."""
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
    try:
        conn.request(method, path, headers=headers or {})
        r = conn.getresponse()
        r.read()
        return r.status, r.getheader("Set-Cookie")
    finally:
        conn.close()


def test_wrong_cookie_and_wrong_link_refused(api):
    assert _raw(api, "GET", "/api/jobs", {"Cookie": "emt=nope"})[0] == 401
    status, cookie = _raw(api, "GET", "/?k=nope")
    assert status == 401 and cookie is None


def test_foreign_origin_refused(api):
    assert api.json("GET", "/api/jobs", headers={"Origin": "http://evil.example"})[0] == 403
    ok = api.json("GET", "/api/jobs", headers={"Origin": f"http://127.0.0.1:{api.port}"})
    assert ok[0] == 200
    folder = _demo(api)
    post = {"folder": str(folder), "event": {"type": "message", "text": "x"}}
    assert api.json("POST", "/api/inbox", post, headers={"Origin": "http://evil.example"})[0] == 403
    assert js.read_events(folder) == []


def test_foreign_host_refused(api):
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
    conn.request("GET", "/api/ping", headers={"Host": f"evil.example:{api.port}"})
    r = conn.getresponse()
    r.read()
    assert r.status == 403
    conn.close()


def test_static_index_served(api):
    status, headers, data = api.call("GET", "/", token=None)
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert _raw(api, "GET", "/static/index.html")[0] == 200
    assert _raw(api, "GET", "/static/missing.js")[0] == 404
    assert _raw(api, "GET", "/static/../server.py")[0] == 403
    assert _raw(api, "GET", "/static/%2e%2e/server.py")[0] == 403
    assert _raw(api, "GET", "/static/%2e%2e%2fserver.py")[0] == 403
    # a backslash is a separator on Windows (escape: 403); elsewhere it is part of a name that does not exist
    assert _raw(api, "GET", "/static/..%5Cserver.py")[0] == (403 if sys.platform == "win32" else 404)


def test_job_roundtrip_and_etag(api):
    folder = _demo(api)
    status, headers, body = api.call("GET", "/api/job" + _q(folder=folder))
    assert status == 200
    data = json.loads(body)
    assert data["job"]["card"]["product"] == "Cereza Ácida"
    assert data["listening"] is None and data["pending"] == [] and data["keyframes"] == {}
    assert data["storyboard"] is None and data["gui"] == {} and data["outputs"] == {}
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    etag = headers["ETag"]
    assert api.call("GET", "/api/job" + _q(folder=folder), headers={"If-None-Match": etag})[0] == 304
    js.append_event(folder, {"type": "message", "text": "hola"})
    assert api.call("GET", "/api/job" + _q(folder=folder), headers={"If-None-Match": etag})[0] == 200


def test_job_carries_the_generators_table(api):
    import generators
    folder = _demo(api)
    data = api.json("GET", "/api/job" + _q(folder=folder))[1]
    assert data["generators"] == generators.load()
    assert "seedance-2.5" in data["generators"]["generators"]["higgsfield"]["models"]


def test_job_carries_the_early_table(api):
    folder = _demo(api)
    data = api.json("GET", "/api/job" + _q(folder=folder))[1]
    assert data["early"] == js.EARLY and data["early"]["music"] == ["source", "upload"]
    s, ev = api.json("POST", "/api/inbox", {"folder": str(folder), "event": {
        "type": "answer", "step": "captions", "gate": None, "target": "captions:who", "value": "me", "early": True}})
    assert s == 200 and ev["early"] is True and "stale" not in ev


def test_etag_ignores_listening_heartbeat(api):
    folder = _demo(api)
    js.write_listening(folder, "script")
    try:
        status, headers, body = api.call("GET", "/api/job" + _q(folder=folder))
        assert status == 200 and json.loads(body)["listening"]["step"] == "script"
        time.sleep(0.02)
        js.write_listening(folder, "script")  # heartbeat: new beat, same pid/step/since
        assert api.call("GET", "/api/job" + _q(folder=folder), headers={"If-None-Match": headers["ETag"]})[0] == 304
        js.clear_listening(folder)  # Claude stops listening: the page must hear about it
        assert api.call("GET", "/api/job" + _q(folder=folder), headers={"If-None-Match": headers["ETag"]})[0] == 200
    finally:
        js.clear_listening(folder)


def test_output_outside_roots_not_read(api, tmp_path):
    folder = _demo(api)
    (tmp_path / "elsewhere.json").write_text('{"secret": 1}', encoding="utf-8")
    job = js.load(folder)
    job["outputs"] = {"brief": {"checklist": {"path": str(tmp_path / "elsewhere.json"), "at": "x"}}}
    js.save(folder, job)
    assert api.json("GET", "/api/job" + _q(folder=folder))[1]["outputs"] == {"brief": {"checklist": None}}


def test_write_routes_need_a_video_folder(api):
    (api.root / "_practice").mkdir()
    bad = [".git", ".claude/edit-mo-to", "docs", "PYNK_AI_UGC_Studio", "_misc", "Nativia/sub/deeper"]
    for rel in bad + ["_practice/run1"]:
        js.save(api.root / rel, js.new_job(api.root / rel, "c", "p"))  # a job.json does not make it a video folder
    for rel in bad + [""]:
        folder = api.root / rel
        ev = {"folder": str(folder), "event": {"type": "message"}}
        assert api.json("POST", "/api/inbox", ev)[0] == 403, rel
        assert api.json("POST", "/api/gui", {"folder": str(folder), "patch": {"a": 1}})[0] == 403, rel
        assert api.json("PUT", "/api/upload" + _q(folder=folder, kind="refs", name="x.pdf"), raw=b"x")[0] == 403, rel
        assert api.json("GET", "/api/job" + _q(folder=folder))[0] == 403, rel
    assert not (api.root / ".git" / "refs").exists() and not (api.root / "docs" / "refs").exists()
    practice = api.root / "_practice" / "run1"
    assert api.json("POST", "/api/inbox", {"folder": str(practice), "event": {"type": "message"}})[0] == 200
    missing = {"folder": str(api.root / "Not There"), "event": {"type": "message"}}
    assert api.json("POST", "/api/inbox", missing)[0] == 404
    assert not (api.root / "Not There").exists()
    assert api.json("POST", "/api/inbox", {"folder": "relative/x", "event": {"type": "message"}})[0] == 400


def test_job_outputs_parsed(api):
    folder = _demo(api)
    rel = ".edit-mo-to/outputs/brief-checklist.json"
    (folder / rel).parent.mkdir(parents=True)
    (folder / rel).write_text(json.dumps({"style": "ugc"}), encoding="utf-8")
    job = js.load(folder)
    job["outputs"] = {"brief": {"checklist": {"path": rel, "at": "x"}}}
    js.save(folder, job)
    data = api.json("GET", "/api/job" + _q(folder=folder))[1]
    assert data["outputs"] == {"brief": {"checklist": {"style": "ugc"}}}


def test_job_outside_root_refused(api, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    js.save(outside, js.new_job(outside, "c", "p"))
    assert api.json("GET", "/api/job" + _q(folder=outside))[0] == 403


def test_inbox_post_assigns_seq(api):
    folder = _demo(api)
    s1, e1 = api.json("POST", "/api/inbox", {"folder": str(folder), "event": {"type": "message", "text": "a"}})
    s2, e2 = api.json("POST", "/api/inbox", {"folder": str(folder), "event": {"type": "comment", "text": "b"}})
    assert (s1, s2) == (200, 200) and (e1["seq"], e2["seq"]) == (1, 2) and e1["at"]
    assert api.json("POST", "/api/inbox", {"folder": str(folder), "event": {"type": "nope"}})[0] == 400


def test_pending_lists_unhandled_edits(api):
    folder = _demo(api)
    for t in ("edit", "message", "approve", "action", "comment"):
        js.append_event(folder, {"type": t})
    job = js.load(folder)
    job["handled"] = [3]
    js.save(folder, job)
    data = api.json("GET", "/api/job" + _q(folder=folder))[1]
    assert [e["type"] for e in data["pending"]] == ["edit", "action"]


def test_gui_patch_merges(api):
    folder = _demo(api)
    assert api.json("POST", "/api/gui", {"folder": str(folder), "patch": {"page": "script", "x": 1}}) == \
        (200, {"page": "script", "x": 1})
    assert api.json("POST", "/api/gui", {"folder": str(folder), "patch": {"x": None, "y": 2}}) == \
        (200, {"page": "script", "y": 2})
    assert api.json("GET", "/api/job" + _q(folder=folder))[1]["gui"] == {"page": "script", "y": 2}


def test_keyframe_saved_outside_shows_up(api):
    folder = _demo(api)
    first = api.call("GET", "/api/job" + _q(folder=folder))
    (folder / "storyboard").mkdir()
    (folder / "storyboard" / "SB-2.png").write_bytes(b"png")
    (folder / "storyboard" / "CHAR-1.webp").write_bytes(b"webp")
    (folder / "storyboard" / "notes.png").write_bytes(b"x")
    status, _, body = api.call("GET", "/api/job" + _q(folder=folder), headers={"If-None-Match": first[1]["ETag"]})
    assert status == 200
    kf = json.loads(body)["keyframes"]
    assert sorted(kf) == ["CHAR-1", "SB-2"]
    assert Path(kf["SB-2"]) == (folder / "storyboard" / "SB-2.png").resolve()
    mt = json.loads(body)["keyframe_mtimes"]
    assert sorted(mt) == ["CHAR-1", "SB-2"]
    assert mt["SB-2"] == (folder / "storyboard" / "SB-2.png").stat().st_mtime_ns


def test_keyframe_replaced_outside_gets_a_new_mtime(api):
    """An SB-n.png overwritten from outside the app changes its mtime, the page's image cache-buster."""
    folder = _demo(api)
    (folder / "storyboard").mkdir()
    img = folder / "storyboard" / "SB-1.png"
    img.write_bytes(b"one")
    os.utime(img, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    first = api.json("GET", "/api/job" + _q(folder=folder))[1]["keyframe_mtimes"]["SB-1"]
    img.write_bytes(b"two")
    os.utime(img, ns=(1_000_000_005_000_000_000, 1_000_000_005_000_000_000))
    second = api.json("GET", "/api/job" + _q(folder=folder))[1]["keyframe_mtimes"]["SB-1"]
    assert first != second and isinstance(second, int)


def test_upload_rules(api):
    folder = _demo(api)
    up = "/api/upload"
    s, d = api.json("PUT", up + _q(folder=folder, kind="keyframe", id="SB-5", name="shot.png"), raw=b"one")
    assert s == 200 and Path(d["path"]) == (folder / "storyboard" / "SB-5.png").resolve()
    s, d = api.json("PUT", up + _q(folder=folder, kind="keyframe", id="SB-5", name="other.png"), raw=b"two")
    assert s == 200 and (folder / "storyboard" / "SB-5.png").read_bytes() == b"two"
    assert sorted(p.name for p in (folder / "storyboard").iterdir()) == ["SB-5.png"]
    assert api.json("PUT", up + _q(folder=folder, kind="refs", name="virus.exe"), raw=b"x")[0] == 415
    assert api.json("PUT", up + _q(folder=folder, kind="keyframe", id="SB-x", name="a.png"), raw=b"x")[0] == 400
    assert api.json("PUT", up + _q(folder=folder, kind="refs", name="../a.pdf"), raw=b"x")[0] == 400
    assert api.json("PUT", up + _q(folder=folder, kind="refs", name=".a.pdf"), raw=b"x")[0] == 400
    for ch in '<>"|?*:':
        assert api.json("PUT", up + _q(folder=folder, kind="refs", name=f"a{ch}b.pdf"), raw=b"x")[0] == 400, ch
    assert api.json("PUT", up + _q(folder=folder, kind="refs", name="nul.pdf"), raw=b"x")[0] == 400
    api.json("PUT", up + _q(folder=folder, kind="refs", name="a.pdf"), raw=b"1")
    s, d = api.json("PUT", up + _q(folder=folder, kind="refs", name="a.pdf"), raw=b"2")
    assert s == 200 and Path(d["path"]).name == "a (2).pdf"
    assert (folder / "refs" / "a.pdf").read_bytes() == b"1"
    events = js.read_events(folder)
    assert events[0]["type"] == "upload" and events[0]["step"] == "storyboard"
    assert events[0]["target"] == "keyframe:SB-5"
    assert events[-1]["step"] == "brief" and events[-1]["target"] == "refs:a.pdf"
    assert events[-1]["value"].endswith("refs/a (2).pdf")
    assert not [p for p in (folder / "refs").iterdir() if p.name.startswith(".")]


def test_upload_too_big_refused_before_reading(api):
    folder = _demo(api)
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
    conn.putrequest("PUT", "/api/upload" + _q(folder=folder, kind="keyframe", id="SB-1", name="a.png"))
    conn.putheader("X-EMT-Token", TOKEN)
    conn.putheader("Content-Length", str(51 * 1024 * 1024))
    conn.endheaders()
    r = conn.getresponse()
    r.read()
    assert r.status == 413
    conn.close()
    assert not (folder / "storyboard" / "SB-1.png").exists()


def test_file_route_blocks_escape(api, tmp_path):
    (tmp_path / "secret").write_text("s", encoding="utf-8")
    assert api.call("GET", "/api/file" + _q(path=f"{api.root}/../secret"))[0] == 403
    (api.root / "x.txt").write_text("hi", encoding="utf-8")
    s, h, body = api.call("GET", "/api/file" + _q(path=api.root / "x.txt"))
    assert s == 200 and body == b"hi" and h["Content-Type"].startswith("text/plain")
    assert api.call("GET", "/api/file" + _q(path=api.root / "missing.txt"))[0] == 404


def test_new_job_conflict(api):
    folder = api.root / "Nativia New"
    body = {"client": "Nativia", "product": "Serum", "folder": str(folder)}
    s, d = api.json("POST", "/api/new", body)
    assert s == 200 and (folder / ".edit-mo-to" / "job.json").is_file()
    assert Path(api.json("GET", "/api/current")[1]["folder"]) == folder.resolve()
    assert Path(d["folder"]) == folder.resolve() and d["job"]["card"]["client"] == "Nativia"
    assert api.json("POST", "/api/new", body)[0] == 409
    assert api.json("POST", "/api/new", {**body, "folder": str(api.root / ".." / "out")})[0] == 403
    for rel in (".git", "docs", "_misc", "a/b"):
        assert api.json("POST", "/api/new", {**body, "folder": str(api.root / rel)})[0] == 403, rel
    assert not (api.root / "a").exists() and not (api.root / ".git").exists()
    practice = {**body, "folder": str(api.root / "_practice" / "run1")}
    assert api.json("POST", "/api/new", practice)[0] == 400  # never creates the _practice parent
    assert not (api.root / "_practice").exists()
    (api.root / "_practice").mkdir()
    assert api.json("POST", "/api/new", practice)[0] == 200
    assert api.json("POST", "/api/new", {**body, "folder": "By Name"})[0] == 200  # a bare name: under root
    assert (api.root / "By Name" / ".edit-mo-to" / "job.json").is_file()


def test_jobs_lists_folders(api):
    folder = _demo(api)
    job = js.load(folder)
    job["card"]["style"] = "ugc"
    job["steps"]["brief"]["state"] = "done"
    job["steps"]["script"]["state"] = "waiting"
    job["gate"] = {"id": "g-1", "title": "Approve", "questions": [{"id": "q", "text": "ok?", "kind": "confirm"}]}
    js.save(folder, job)
    (api.root / "Old").mkdir()
    data = {j["name"]: j for j in api.json("GET", "/api/jobs")[1]}
    assert data[DEMO]["has_job"] and data[DEMO]["client"] == "Uvola" and data[DEMO]["style"] == "ugc"
    assert data[DEMO]["step"] == "script" and data[DEMO]["waiting"] is True
    assert data[DEMO]["progress"] == pytest.approx(1 / 12)
    assert data["Old"]["has_job"] is False and data["Old"]["waiting"] is False


def test_settings_write_only_known_keys(api, tmp_path, monkeypatch):
    cfg = tmp_path / "machine.json"
    cfg.write_text(json.dumps({"_note": "keep", "asr": "mlx", "root": "old"}), encoding="utf-8")
    monkeypatch.setattr(machine, "CONFIG", cfg)
    s, _ = api.json("POST", "/api/settings", {"root": str(api.root), "gui_port": 4811, "evil": "x"})
    assert s == 200
    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert "evil" not in saved and saved["_note"] == "keep" and saved["asr"] == "mlx"
    assert saved["root"] == str(api.root) and saved["gui_port"] == 4811
    assert api.json("POST", "/api/settings", {"gui_port": 80})[0] == 400
    assert api.json("POST", "/api/settings", {"tmp": 5})[0] == 400
    s, d = api.json("POST", "/api/settings", {"capcut_drafts": str(tmp_path / "nowhere")})
    assert s == 400 and "capcut_drafts" in d["error"]
    assert "capcut_drafts" not in json.loads(cfg.read_text(encoding="utf-8"))
    s, d = api.json("GET", "/api/settings")
    assert s == 200 and d["paths"]["root"] == str(api.root) and d["found"]["root"] is True


def test_checks_routes(api, monkeypatch):
    import checks
    monkeypatch.setattr(checks, "setup", lambda: [{"name": "x", "ok": True, "detail": "ok"}])
    monkeypatch.setattr(checks, "capcut_running", lambda: False)
    monkeypatch.setattr(checks, "temp_en_timelines", lambda p: ["Hook A"])
    monkeypatch.setattr(checks.capcut_project, "list_timelines", lambda p: [{"name": "Hook A"}])
    assert api.json("GET", "/api/checks")[1] == [{"name": "x", "ok": True, "detail": "ok"}]
    assert api.json("GET", "/api/capcut")[1] == {"running": False}
    proj = api.root / "proj"
    proj.mkdir()
    assert api.json("GET", "/api/temp-en" + _q(project=proj))[1] == {"timelines": ["Hook A"]}


def test_temp_en_missing_project_is_an_error_not_clean(api):
    """A project path that isn't there must not read as "no TEMP_EN left" (the Export page shows "Could not check")."""
    status, data = api.json("GET", "/api/temp-en" + _q(project=api.root / "no such project"))
    assert status == 404 and "error" in data
    (api.root / "empty").mkdir()  # a folder that is no CapCut project
    assert api.json("GET", "/api/temp-en" + _q(project=api.root / "empty"))[0] == 404


def test_feedback_saved_and_issue_url(api):
    body = {"type": "bug", "title": "Upload fails & stops", "text": "It broke", "step": "storyboard",
            "folder": str(api.root / DEMO)}
    s, d = api.json("POST", "/api/feedback", body)
    assert s == 200
    url = d["issue_url"]
    assert url.startswith("https://github.com/jushuaaang/edit-mo-to/issues/new?")
    assert urllib.parse.urlencode({"title": "Upload fails & stops"}) in url
    assert "labels=bug" in url
    assert DEMO not in urllib.parse.unquote_plus(url) and str(api.root) not in urllib.parse.unquote_plus(url)
    assert "folder" not in d
    items = api.json("GET", "/api/feedback")[1]
    assert [i["title"] for i in items] == ["Upload fails & stops"] and items[0]["at"]
    assert api.json("POST", "/api/feedback", {"type": "rant", "title": "t", "text": "x"})[0] == 400


def test_settings_python_must_be_a_python(api, tmp_path, monkeypatch):
    cfg = tmp_path / "machine.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(machine, "CONFIG", cfg)
    other = tmp_path / "evil.sh"
    other.write_text("x", encoding="utf-8")
    s, d = api.json("POST", "/api/settings", {"python": str(other)})
    assert s == 400 and "python" in d["error"]
    py = tmp_path / "bin" / "python3"
    py.parent.mkdir()
    py.write_text("x", encoding="utf-8")
    assert api.json("POST", "/api/settings", {"python": str(py)})[0] == 200


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_upload_into_a_symlinked_subfolder_refused(api, tmp_path):
    folder = _demo(api)
    outside = tmp_path / "outside"
    outside.mkdir()
    (folder / "vo").symlink_to(outside, target_is_directory=True)
    s, _ = api.json("PUT", "/api/upload" + _q(folder=folder, kind="vo", name="a.mp3"), raw=b"x")
    assert s == 403 and not list(outside.iterdir())
