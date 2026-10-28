"""Task G: tools/elevenlabs_vo.py, the ElevenLabs voiceover (official API, the editor's own key). No network: every
test mocks urllib.request.urlopen. The key is never printed, logged or put in an error."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import elevenlabs_vo as ev  # noqa: E402

KEY = "sk_test_9f8e7d6c5b4a_SECRET"
MP3 = b"ID3\x04\x00fake-mp3-bytes" * 10


@pytest.fixture
def job(tmp_path, monkeypatch):
    folder = tmp_path / "Video A"
    (folder / ".edit-mo-to").mkdir(parents=True)
    (folder / ".edit-mo-to" / "job.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "script.txt"
    script.write_text("Hello there.\nThis is the second line.\n", encoding="utf-8")
    secrets = tmp_path / "secrets.json"
    secrets.write_text(json.dumps({"elevenlabs_api_key": KEY}), encoding="utf-8")
    monkeypatch.setattr(ev, "SECRETS", secrets)
    monkeypatch.setattr(ev, "PREFS", tmp_path / "prefs.json")
    return folder, script, secrets


class _Resp:
    def __init__(self, body=MP3, status=200, ctype="audio/mpeg"):
        self._b, self.status, self.headers = io.BytesIO(body), status, {"Content-Type": ctype}

    def read(self, n=-1):
        return self._b.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture(monkeypatch, resp=None, exc=None):
    seen = {}

    def fake(req, timeout=None):
        seen["url"], seen["headers"] = req.full_url, {k.lower(): v for k, v in req.header_items()}
        seen["body"], seen["method"], seen["timeout"] = req.data, req.get_method(), timeout
        if exc:
            raise exc
        return resp or _Resp()
    monkeypatch.setattr(ev.urllib.request, "urlopen", fake)
    return seen


def _run(argv, capsys):
    code = 0
    try:
        ev.main(argv)
    except SystemExit as e:
        code = e.code or 0
    out = capsys.readouterr()
    return code, out.out, out.err


def test_estimate_counts_characters(job, capsys, monkeypatch):
    _, script, _ = job
    seen = _capture(monkeypatch)
    code, out, err = _run(["estimate", str(script)], capsys)
    text = "Hello there.\nThis is the second line."
    assert code == 0 and json.loads(out) == {"ok": True, "chars": len(text), "credits": len(text)}
    assert seen == {}   # no call for an estimate


def test_make_posts_to_the_tts_endpoint_and_writes_the_mp3(job, capsys, monkeypatch):
    folder, script, _ = job
    seen = _capture(monkeypatch)
    out_path = folder / "vo" / "vo_full.mp3"
    code, out, err = _run(["make", str(script), "--voice", "21m00Tcm4TlvDq8ikWAM", "--out", str(out_path)], capsys)
    assert code == 0, out + err
    got = json.loads(out)
    assert got == {"ok": True, "path": out_path.resolve().as_posix(), "chars": 37}
    assert out_path.read_bytes() == MP3
    assert seen["method"] == "POST"
    assert seen["url"] == "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM?output_format=mp3_44100_128"
    assert seen["headers"]["xi-api-key"] == KEY
    assert seen["headers"]["content-type"] == "application/json" and seen["headers"]["accept"] == "audio/mpeg"
    assert json.loads(seen["body"]) == {"text": "Hello there.\nThis is the second line.", "model_id": "eleven_multilingual_v2"}
    assert seen["timeout"] and seen["timeout"] > 0
    assert KEY not in out + err
    assert not list((folder / "vo").glob("*.part"))


def test_model_flag_and_prefs_defaults(job, capsys, monkeypatch):
    folder, script, _ = job
    ev.PREFS.write_text(json.dumps({"elevenlabs_voice": "VoiceFromPrefs1", "elevenlabs_model": "eleven_flash_v2_5"}),
                        encoding="utf-8")
    seen = _capture(monkeypatch)
    code, out, _ = _run(["make", str(script), "--out", str(folder / "vo" / "a.mp3")], capsys)
    assert code == 0, out
    assert "/text-to-speech/VoiceFromPrefs1?" in seen["url"]
    assert json.loads(seen["body"])["model_id"] == "eleven_flash_v2_5"
    code, out, _ = _run(["make", str(script), "--voice", "V2", "--model", "eleven_v3", "--out", str(folder / "vo" / "b.mp3")],
                        capsys)
    assert code == 0 and "/text-to-speech/V2?" in seen["url"] and json.loads(seen["body"])["model_id"] == "eleven_v3"


def test_no_voice_anywhere_is_refused(job, capsys, monkeypatch):
    folder, script, _ = job
    seen = _capture(monkeypatch)
    code, out, _ = _run(["make", str(script), "--out", str(folder / "vo" / "a.mp3")], capsys)
    assert code == 1 and "voice" in json.loads(out)["error"] and seen == {}


@pytest.mark.parametrize("raw", [None, "", "not json", "[]", '{"elevenlabs_api_key": ""}', '{"other": "x"}'])
def test_key_not_set(job, capsys, monkeypatch, raw):
    folder, script, secrets = job
    if raw is None:
        secrets.unlink()
    else:
        secrets.write_text(raw, encoding="utf-8")
    seen = _capture(monkeypatch)
    code, out, err = _run(["make", str(script), "--voice", "V", "--out", str(folder / "vo" / "a.mp3")], capsys)
    assert code == 1 and json.loads(out) == {"ok": False, "error": "ElevenLabs key not set"}
    assert seen == {}


def test_http_error_shows_status_and_message_with_the_key_redacted(job, capsys, monkeypatch):
    folder, script, _ = job
    body = json.dumps({"detail": {"status": "invalid_api_key", "message": f"Invalid API key: {KEY}"}}).encode()
    err = urllib.error.HTTPError("https://api.elevenlabs.io/v1/text-to-speech/V", 401, "Unauthorized",
                                 {"Content-Type": "application/json"}, io.BytesIO(body))
    _capture(monkeypatch, exc=err)
    target = folder / "vo" / "a.mp3"
    code, out, e = _run(["make", str(script), "--voice", "V", "--out", str(target)], capsys)
    msg = json.loads(out)["error"]
    assert code == 1 and "401" in msg and "Invalid API key" in msg and "[redacted]" in msg
    assert KEY not in out + e
    assert not target.exists() and not list((folder / "vo").glob("*"))


def test_http_error_with_a_plain_detail_and_quota(job, capsys, monkeypatch):
    folder, script, _ = job
    body = json.dumps({"detail": "quota_exceeded"}).encode()
    _capture(monkeypatch, exc=urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(body)))
    code, out, _ = _run(["make", str(script), "--voice", "V", "--out", str(folder / "vo" / "a.mp3")], capsys)
    assert code == 1 and "429" in json.loads(out)["error"] and "quota_exceeded" in json.loads(out)["error"]


def test_network_error_is_redacted(job, capsys, monkeypatch):
    folder, script, _ = job
    _capture(monkeypatch, exc=urllib.error.URLError(f"weird failure {KEY}"))
    code, out, err = _run(["make", str(script), "--voice", "V", "--out", str(folder / "vo" / "a.mp3")], capsys)
    assert code == 1 and "ElevenLabs" in json.loads(out)["error"] and KEY not in out + err


def test_unexpected_reply_is_not_saved(job, capsys, monkeypatch):
    folder, script, _ = job
    _capture(monkeypatch, resp=_Resp(body=json.dumps({"x": KEY}).encode(), ctype="application/json"))
    target = folder / "vo" / "a.mp3"
    code, out, err = _run(["make", str(script), "--voice", "V", "--out", str(target)], capsys)
    assert code == 1 and KEY not in out + err and not target.exists()
    _capture(monkeypatch, resp=_Resp(body=b""))
    code, out, _ = _run(["make", str(script), "--voice", "V", "--out", str(target)], capsys)
    assert code == 1 and not target.exists()


@pytest.mark.parametrize("where", ["outside", "not_vo", "no_job", "dotdot", "not_mp3", "exists"])
def test_out_must_be_in_the_video_folders_vo(job, capsys, monkeypatch, tmp_path, where):
    folder, script, _ = job
    seen = _capture(monkeypatch)
    plain = tmp_path / "Plain"
    (plain / "vo").mkdir(parents=True)
    (folder / "vo").mkdir(exist_ok=True)
    (folder / "vo" / "taken.mp3").write_bytes(b"old")
    out_path = {"outside": tmp_path / "a.mp3", "not_vo": folder / "music" / "a.mp3", "no_job": plain / "vo" / "a.mp3",
                "dotdot": folder / "vo" / ".." / "a.mp3", "not_mp3": folder / "vo" / "a.wav",
                "exists": folder / "vo" / "taken.mp3"}[where]
    code, out, _ = _run(["make", str(script), "--voice", "V", "--out", str(out_path)], capsys)
    assert code == 1, where
    assert seen == {}, where       # refused before any call (no credits spent)
    assert (folder / "vo" / "taken.mp3").read_bytes() == b"old"


def test_a_symlinked_vo_folder_cannot_lead_out(job, capsys, monkeypatch, tmp_path):
    folder, script, _ = job
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (folder / "vo").symlink_to(elsewhere, target_is_directory=True)
    seen = _capture(monkeypatch)
    code, _, _ = _run(["make", str(script), "--voice", "V", "--out", str(folder / "vo" / "a.mp3")], capsys)
    assert code == 1 and seen == {} and not (elsewhere / "a.mp3").exists()


def test_voice_id_is_checked(job, capsys, monkeypatch):
    folder, script, _ = job
    seen = _capture(monkeypatch)
    code, out, _ = _run(["make", str(script), "--voice", "../v1/user", "--out", str(folder / "vo" / "a.mp3")], capsys)
    assert code == 1 and seen == {}


def test_empty_or_huge_script_is_refused(job, capsys, monkeypatch, tmp_path):
    folder, _, _ = job
    seen = _capture(monkeypatch)
    empty = tmp_path / "e.txt"
    empty.write_text("  \n", encoding="utf-8")
    assert _run(["make", str(empty), "--voice", "V", "--out", str(folder / "vo" / "a.mp3")], capsys)[0] == 1
    big = tmp_path / "b.txt"
    big.write_text("a" * (ev.MAX_CHARS + 1), encoding="utf-8")
    assert _run(["make", str(big), "--voice", "V", "--out", str(folder / "vo" / "a.mp3")], capsys)[0] == 1
    assert seen == {}


def test_source_never_prints_or_logs_the_key():
    src = (TOOLS / "elevenlabs_vo.py").read_text(encoding="utf-8")
    assert "import requests" not in src and "logging" not in src
    for line in src.splitlines():
        if "print(" in line:
            assert "key" not in line.lower() or "key not set" in line.lower(), line
