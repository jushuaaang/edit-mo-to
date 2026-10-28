"""The voiceover through the official ElevenLabs API, with the editor's own key ("Generate for me", Joshua only).
Standard library only.

    estimate <script.txt>
        {"ok": true, "chars": N, "credits": N}   (about 1 credit per character; nothing is sent)
    make <script.txt> [--voice <voice id>] [--model <model id>] --out "<video folder>/vo/<name>.mp3"
        POST the script to ElevenLabs text-to-speech, write the mp3, print {"ok": true, "path", "chars"}.
        --voice / --model default to this computer's Settings (prefs elevenlabs_voice / elevenlabs_model);
        the model's default is eleven_multilingual_v2.

The key comes from .claude/edit-mo-to/secrets.json ({"elevenlabs_api_key": "..."}, git-ignored, filled in by the
editor). It is sent only in the xi-api-key header and never printed, logged or put in an error (any reply text is
redacted). --out must be a new .mp3 directly in the vo/ folder of a video folder that has a job (.edit-mo-to/job.json);
anything else is refused before any call, so no credits are spent. Errors: {"ok": false, "error": ...}, exit 1.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import machine  # noqa: E402

SECRETS = Path(machine.CONFIG).parent / "secrets.json"
PREFS = Path(os.environ.get("EDIT_MO_TO_GUI_TMP") or machine.PATHS["tmp"]) / "gui" / "prefs.json"
API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
DEFAULT_MODEL = "eleven_multilingual_v2"
MAX_CHARS = 10000          # ElevenLabs' per-request limit for the multilingual model; split a longer script
MAX_AUDIO = 200 << 20
TIMEOUT = 300
VOICE = re.compile(r"[A-Za-z0-9]{1,64}")
MODEL = re.compile(r"[a-z0-9_]{1,64}")


class Refused(Exception):
    pass


def _fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    sys.exit(1)


def _redact(text: str, key: "str | None") -> str:
    text = str(text)
    if key:
        text = text.replace(key, "[redacted]")
    return text[:300]


def read_script(path: str) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8-sig").strip()
    except (OSError, ValueError) as e:
        raise Refused(f"can't read the script: {path}") from e
    if not text:
        raise Refused("the script is empty")
    return text


def _key() -> str:
    try:
        data = json.loads(Path(SECRETS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused("ElevenLabs key not set") from None
    value = data.get("elevenlabs_api_key") if isinstance(data, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise Refused("ElevenLabs key not set")
    return value.strip()


def _prefs() -> dict:
    try:
        data = json.loads(Path(PREFS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def check_out(raw: str) -> Path:
    """A new .mp3 directly in <video folder>/vo/ (the folder has .edit-mo-to/job.json); vo/ may not lead elsewhere."""
    out = Path(raw)
    if ".." in out.parts or out.suffix.lower() != ".mp3":
        raise Refused("--out must be a .mp3 file in the video folder's vo/ folder")
    out = out.absolute()
    vo, video = out.parent, out.parent.parent
    if vo.name != "vo" or not (video / ".edit-mo-to" / "job.json").is_file():
        raise Refused("--out must be in the vo/ folder of a video folder with a job")
    if vo.exists() and (vo.is_symlink() or vo.resolve() != video.resolve() / "vo"):
        raise Refused("the vo/ folder leads outside the video folder")
    if out.exists() or out.is_symlink():
        raise Refused(f"{out.name} already exists in vo/; pick a new name")
    return out


def make(script: str, voice: "str | None", model: "str | None", out_raw: str) -> dict:
    text = read_script(script)
    if len(text) > MAX_CHARS:
        raise Refused(f"the script has {len(text)} characters; ElevenLabs takes at most {MAX_CHARS} per file. Split it.")
    prefs = _prefs()
    voice = voice or prefs.get("elevenlabs_voice")
    model = model or prefs.get("elevenlabs_model") or DEFAULT_MODEL
    if not isinstance(voice, str) or not voice:
        raise Refused("no voice: set the ElevenLabs voice id in Settings, or pass --voice")
    if not VOICE.fullmatch(voice):
        raise Refused("the voice id must be letters and digits only")
    if not isinstance(model, str) or not MODEL.fullmatch(model):
        raise Refused("the model id must be lowercase letters, digits and _ only")
    out = check_out(out_raw)
    key = _key()
    req = urllib.request.Request(API.format(voice=urllib.parse.quote(voice, safe="")), method="POST",
                                 data=json.dumps({"text": text, "model_id": model}).encode("utf-8"),
                                 headers={"xi-api-key": key, "Content-Type": "application/json",
                                          "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            ctype = (r.headers.get("Content-Type") or "") if hasattr(r.headers, "get") else ""
            audio = r.read(MAX_AUDIO + 1)
    except urllib.error.HTTPError as e:
        try:
            body = e.read(4096).decode("utf-8", "replace")
            detail = json.loads(body).get("detail")
            msg = detail.get("message") or detail.get("status") if isinstance(detail, dict) else detail
        except (ValueError, AttributeError, OSError):
            msg = None
        raise Refused(_redact(f"ElevenLabs said {e.code}: {msg or e.reason}", key)) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        reason = getattr(e, "reason", None) or type(e).__name__
        raise Refused(_redact(f"could not reach ElevenLabs ({reason})", key)) from None
    if not ctype.startswith("audio/") or not audio or len(audio) > MAX_AUDIO:
        raise Refused("ElevenLabs sent no audio; nothing was saved")
    out.parent.mkdir(exist_ok=True)
    part = out.with_name(f".{out.name}.part")
    try:
        part.write_bytes(audio)
        os.replace(part, out)
    finally:
        part.unlink(missing_ok=True)
    return {"path": out.resolve().as_posix(), "chars": len(text)}


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate")
    e.add_argument("script")
    m = sub.add_parser("make")
    m.add_argument("script")
    m.add_argument("--voice")
    m.add_argument("--model")
    m.add_argument("--out", required=True)
    a = p.parse_args(argv)
    try:
        if a.cmd == "estimate":
            n = len(read_script(a.script))
            result = {"chars": n, "credits": n}
        else:
            result = make(a.script, a.voice, a.model, a.out)
    except Refused as err:
        _fail(str(err))
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
