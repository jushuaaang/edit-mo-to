import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import captions  # noqa: E402


def _w(spec):
    """[(word, start, end), ...] -> word dicts."""
    return [{"word": w, "start": s, "end": e} for w, s, e in spec]


def _texts(chunks):
    return [c["text"] for c in chunks]


def test_chunks_cut_at_punctuation_and_pause():
    words = _w([("Hi", 0.0, 0.2), ("there,", 0.25, 0.5), ("friend.", 0.55, 0.9),
                ("How", 1.3, 1.5), ("are", 1.55, 1.7), ("you", 1.75, 2.0)])
    out = captions.chunk(words)
    assert _texts(out) == ["Hi there, friend.", "How are you"]
    assert out[0]["start"] == 0.0
    assert out[0]["end"] == pytest.approx(1.3)          # gap 0.4 is under the long pause: held to the next chunk
    assert out[1]["end"] == pytest.approx(2.3)
    assert [w["word"] for w in out[1]["words"]] == ["How", "are", "you"]


def test_no_one_word_orphan_and_number_glue():
    words = _w([("Save", 0.0, 0.3), ("50", 0.35, 0.6), ("%", 0.6, 0.9), ("today", 0.95, 1.3), ("now", 1.35, 1.6)])
    out = captions.chunk(words)
    assert all(len(c["words"]) > 1 for c in out)
    assert any(["50", "%"] == [w["word"] for w in c["words"]][i:i + 2]
               for c in out for i in range(len(c["words"])))
    assert " ".join(_texts(out)) == "Save 50 % today now"


def test_short_chunk_merges():
    # "gamma delta," is on screen 0.3 s: it joins its neighbour in the same sentence
    words = _w([("Alpha", 0.0, 0.3), ("beta,", 0.35, 0.7), ("gamma", 0.8, 0.9), ("delta,", 0.92, 1.0),
                ("epsilon", 1.1, 1.4), ("zeta", 1.45, 1.7), ("eta.", 1.75, 2.1)])
    out = captions.chunk(words)
    assert "gamma delta," not in _texts(out)
    assert any("gamma delta," in t and t != "gamma delta," for t in _texts(out))
    assert " ".join(_texts(out)) == "Alpha beta, gamma delta, epsilon zeta eta."


def test_chunk_respects_max_chars():
    words = _w([(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate("extraordinarily complicated internationalisation considerations.".split())])
    out = captions.chunk(words, max_words=4, max_chars=22)
    assert all(len(c["text"]) <= 44 or len(c["words"]) == 1 for c in out)


def test_to_timeline_follows_a_trim():
    dump = {"segments": [
        {"track": "vo", "track_type": "audio", "at": 0.0, "duration": 2.0, "src_in": 0.0, "speed": 1.0},
        {"track": "vo", "track_type": "audio", "at": 2.0, "duration": 3.0, "src_in": 4.0, "speed": 1.0},
        {"track": "music", "track_type": "audio", "at": 0.0, "duration": 9.0, "src_in": 0.0, "speed": 1.0},
    ]}
    words = _w([("cut", 3.0, 3.4), ("kept", 4.5, 4.9)])
    kept, dropped = captions.to_timeline(words, dump)
    assert [w["word"] for w in dropped] == ["cut"]
    assert [w["word"] for w in kept] == ["kept"]
    assert kept[0]["start"] == pytest.approx(2.5) and kept[0]["end"] == pytest.approx(2.9)


def test_to_timeline_src_in_none_and_speed():
    dump = {"segments": [{"track": "vo_1", "track_type": "audio", "at": 1.0, "duration": 2.0, "src_in": None, "speed": 2.0}]}
    kept, dropped = captions.to_timeline(_w([("a", 1.0, 2.0), ("b", 3.9, 4.5)]), dump)
    assert [(w["start"], w["end"]) for w in kept] == [(1.5, 2.0)]
    assert [w["word"] for w in dropped] == ["b"]


def test_to_timeline_without_vo_segments_uses_vo_in():
    kept, dropped = captions.to_timeline(_w([("a", 0.5, 0.8), ("b", 2.0, 2.4)]), {"segments": []}, vo_in=1.0)
    assert [w["word"] for w in dropped] == ["a"]
    assert kept[0]["start"] == pytest.approx(1.0) and kept[0]["end"] == pytest.approx(1.4)


def test_script_words_replace_asr_spelling():
    asr = _w([("It's", 0.0, 0.3), ("seventy", 0.4, 0.8), ("percent", 0.85, 1.2), ("off.", 1.25, 1.5)])
    out = captions.script_words(asr, ["It's 70 % off."])
    assert [w["word"] for w in out] == ["It's", "70", "%", "off."]
    assert (out[1]["start"], out[1]["end"]) == (0.4, 0.8)
    assert (out[2]["start"], out[2]["end"]) == (0.85, 1.2)
    assert all(w["line"] == 0 for w in out)


def test_script_words_fill_missed_words_and_mark_lines():
    asr = _w([("Hello", 0.0, 0.4), ("world.", 0.5, 0.9), ("Bye", 1.5, 1.8)])
    out = captions.script_words(asr, ["Hello big world.", "Bye now"])
    assert [w["word"] for w in out] == ["Hello", "big", "world.", "Bye", "now"]
    assert [w["line"] for w in out] == [0, 0, 0, 1, 1]
    assert out[1]["start"] >= out[0]["end"] - 1e-9 and out[1]["end"] <= out[2]["start"] + 1e-9
    assert out[4]["start"] >= out[3]["end"] - 1e-9
    # a script line end is a hard stop for the chunker
    assert _texts(captions.chunk(out)) == ["Hello big world.", "Bye now"]


def test_temp_en_rows_one_per_line():
    lines = [{"line": "Ciao a tutti", "start": 0.5, "end": 1.7, "matched": True},
             {"line": "Come state?", "start": 2.0, "end": 3.0, "matched": True}]
    rows = captions.temp_en_rows(lines, ["Hi everyone", "How are you?"])
    assert rows == [{"text": "Hi everyone", "at": 0.5, "duration": pytest.approx(1.2), "style": "temp_en"},
                    {"text": "How are you?", "at": 2.0, "duration": pytest.approx(1.0), "style": "temp_en"}]


def test_temp_en_count_mismatch_raises():
    with pytest.raises(ValueError):
        captions.temp_en_rows([{"line": "a", "start": 0, "end": 1, "matched": True}], ["a", "b"])


def test_cli_temp_en(tmp_path, capsys):
    vo = tmp_path / "vo.json"
    vo.write_text(json.dumps({"words": [], "lines": [{"line": "Hola", "start": 0.0, "end": 1.0, "matched": True}]}), encoding="utf-8")
    en = tmp_path / "script_en.txt"
    en.write_text("Hello\n\n", encoding="utf-8")
    out = tmp_path / "rows.json"
    captions.main(["temp-en", str(vo), str(en), "--out", str(out)])
    printed = json.loads(capsys.readouterr().out)
    assert printed["rows"] == 1 and Path(printed["out"]) == out
    assert json.loads(out.read_text(encoding="utf-8"))[0]["text"] == "Hello"


def test_cli_chunks_uses_timeline_dump(tmp_path, capsys, monkeypatch):
    vo = tmp_path / "vo.json"
    vo.write_text(json.dumps({"words": _w([("Hi", 0.0, 0.2), ("there.", 0.25, 0.6), ("Gone", 3.0, 3.4), ("now.", 3.45, 3.8)])}), encoding="utf-8")
    script = tmp_path / "script.txt"
    script.write_text("Hi there.\nGone now.\n", encoding="utf-8")
    dump = {"segments": [{"track": "vo", "track_type": "audio", "at": 0.0, "duration": 2.0, "src_in": 0.0, "speed": 1.0}]}
    monkeypatch.setattr(captions.capcut_project, "segments", lambda project, name, search_dirs=(): dump)
    out = tmp_path / "chunks.json"
    captions.main(["chunks", str(vo), str(script), str(tmp_path), "Main", "--out", str(out)])
    printed = json.loads(capsys.readouterr().out)
    assert printed["chunks"] == 1
    assert [w["word"] for w in printed["dropped_words"]] == ["Gone", "now."]
    assert _texts(json.loads(out.read_text(encoding="utf-8"))["chunks"]) == ["Hi there."]
