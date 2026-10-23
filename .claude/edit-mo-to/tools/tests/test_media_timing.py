import json
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import media_timing as mt  # noqa: E402


@pytest.mark.parametrize("seconds,expected", [(7.4, "7:12"), (0, "0:00"), (59.999, "1:00:00"), (75.4, "1:15:12"), (59.5, "59:15"), (1.5, "1:15"), (2.0333, "2:01")])
def test_to_sf(seconds, expected):
    assert mt.to_sf(seconds) == expected


def test_to_sf_other_fps():
    assert mt.to_sf(1.5, fps=24) == "1:12"


def _words(text, step=0.5):
    return [{"word": w, "start": i * step, "end": i * step + 0.4} for i, w in enumerate(text.split())]


def test_align_lines_basic():
    words = _words("Hello, world! This is great.")
    out = mt.align_lines(words, ["hello world", "This is GREAT"])
    assert [o["matched"] for o in out] == [True, True]
    assert out[0]["start"] == 0.0 and out[0]["end"] == pytest.approx(0.9)
    assert out[1]["start"] == 1.0 and out[1]["end"] == pytest.approx(2.4)
    assert out[1]["start_sf"] == "1:00" and out[1]["duration"] == pytest.approx(1.4)


def test_align_lines_flags_unmatched_line():
    words = _words("first line here third line here")
    out = mt.align_lines(words, ["first line here", "completely absent words", "third line here"])
    assert [o["matched"] for o in out] == [True, False, True]
    assert out[0]["end"] <= out[1]["start"] <= out[1]["end"] <= out[2]["start"]


def test_align_lines_tolerates_small_mistakes():
    words = _words("this serum changed my skin in two weeks")
    out = mt.align_lines(words, ["this serum changed my skin in 2 weeks"])
    assert out[0]["matched"] is True
    assert out[0]["end"] == pytest.approx(3.9)


def test_vo_report_includes_words_and_lines():
    words = _words("hello world this is great")
    rep = mt.vo_report(words, ["hello world", "this is great"])
    assert [l["matched"] for l in rep["lines"]] == [True, True]
    assert [w["word"] for w in rep["words"]] == ["hello", "world", "this", "is", "great"]
    assert rep["words"][2]["start_sf"] == "1:00"
    assert rep["total"] == mt.to_sf(2.4)


def test_vo_report_without_script_has_no_lines():
    rep = mt.vo_report(_words("just words"), None)
    assert "lines" not in rep and len(rep["words"]) == 2


def test_beats_on_click_track(tmp_path):
    sr, bpm, secs = 22050, 120, 8
    y = np.zeros(sr * secs, dtype=np.float32)
    for t in np.arange(0, secs, 60 / bpm):
        i = int(t * sr)
        y[i:i + 200] = 0.9
    path = tmp_path / "click.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())
    out = mt.beats(path)
    assert abs(out["tempo"] - 120) <= 2
    assert len(out["beats"]) == len(out["beats_sf"]) >= 10


def test_transcribe_uses_cache(tmp_path, monkeypatch):
    import machine

    monkeypatch.setattr(machine, "TMP", tmp_path)
    clip = tmp_path / "clip.wav"
    clip.write_bytes(b"not really audio")
    words = [{"word": "cached", "start": 0.0, "end": 0.4}]
    path = mt._cache_path(clip)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(words), encoding="utf-8")
    assert mt.transcribe(clip) == words  # served from cache, whisper never runs
    clip.write_bytes(b"edited file")  # new size -> new key, so a changed file is re-transcribed
    assert mt._cache_path(clip) != path


def test_compact_lines_and_words():
    rep = {"lines": [{"line": "Hi there", "start_sf": "0:00", "end_sf": "0:20", "matched": True}],
           "words": [{"word": "Hi", "start": 0.0, "end": 0.3}], "total": "0:20"}
    out = mt.compact(rep)
    assert "# lines" in out and "# words" in out
    assert "1|0:00|0:20|1|Hi there" in out and "Hi|0|9" in out


def test_backend_selection(monkeypatch, tmp_path):
    import types

    seen = {}

    def fake_transcribe(path, **kw):
        seen.update(kw)
        return {"segments": [{"words": [{"word": " Hi", "start": 0.0, "end": 0.3}, {"word": "there ", "start": 0.4, "end": 0.8}]}]}

    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=fake_transcribe))
    monkeypatch.setitem(mt.PATHS, "asr", "mlx")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    words = mt.transcribe(audio, cache=False)
    assert words == [{"word": "Hi", "start": 0.0, "end": 0.3}, {"word": "there", "start": 0.4, "end": 0.8}]
    assert seen["path_or_hf_repo"] == "mlx-community/whisper-large-v3-turbo" and seen["word_timestamps"] is True


def test_compact_cli_writes_utf8(tmp_path):
    """stdout must be UTF-8 even when the console default is cp1252 (em dash used to come out as 0x97)."""
    import subprocess
    script = tmp_path / "s.txt"
    script.write_text("Hi there — friend\n", encoding="utf-8")
    code = ("import sys; sys.path.insert(0, %r); import media_timing as mt\n"
            "mt.transcribe = lambda p, cache=True: [{'word': 'Hi', 'start': 0.0, 'end': 0.3}]\n"
            "mt.main(['vo', 'x.mp3', %r, '--compact'])\n") % (str(Path(__file__).resolve().parents[1]), str(script))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, env={**__import__("os").environ, "PYTHONIOENCODING": "cp1252"})
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "—" in r.stdout.decode("utf-8")
