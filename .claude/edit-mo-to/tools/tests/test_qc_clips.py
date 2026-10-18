import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qc_clips as qc  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


@pytest.mark.parametrize("s,expected", [("2:22", 2 + 22 / 30), ("0:00", 0.0), ("1:02:15", 62.5), ("2.5", 2.5)])
def test_parse_sf(s, expected):
    assert qc.parse_sf(s) == pytest.approx(expected)


def test_parse_use():
    assert qc.parse_use("0:00-2:15", 4.0) == pytest.approx((0.0, 2.5))
    assert qc.parse_use([1, 9], 4.0) == (1.0, 4.0)
    assert qc.parse_use(None, 4.0) == (0.0, 4.0)


def test_title_words_strips_flow_suffix():
    assert qc.title_words("Woman_scooping_powder_in_kitchen_202610151230") == \
        ["Woman", "scooping", "powder", "in", "kitchen"]
    assert qc.title_words("Hairstylist_at_chair_2026-10-15 (1)") == ["Hairstylist", "at", "chair"]


def test_check_specs():
    cfg = {"width": 1080, "height": 1920, "fps": 24, "length_tolerance": 0.1}
    good = {"width": 1080, "height": 1920, "fps": 24.0, "duration": 4.0}
    assert qc.check_specs(good, {"length": 4}, cfg) == []
    bad = {"width": 720, "height": 1280, "fps": 30.0, "duration": 8.0}
    flags = qc.check_specs(bad, {"length": 4}, cfg)
    assert [f.split()[0] for f in flags] == ["length", "size", "fps"]


def test_check_specs_aspect_only_without_size():
    assert qc.check_specs({"width": 1920, "height": 1080, "fps": 24, "duration": 4}, {}, {})[0].endswith("not 9:16")


def test_classify_text():
    allowed = ["Fascora", "Fascia-First Formula", "Boswellia + Curcumin"]
    lines = [("Fascora", 0.99), ("Boincollia +Curcunon", 0.94), ("HAIR HEAR", 0.95), ("品", 0.76),
             ("noise", 0.3), ("9:41", 0.9), ("FASCIA-FIRST FORMULA", 0.95)]
    out = qc.classify_text(lines, allowed)
    assert [(o["kind"], o["text"]) for o in out] == [
        ("garbled", "Boincollia +Curcunon"), ("text", "HAIR HEAR"), ("phone", "9:41")]
    assert out[0]["near"] == "curcumin"


def test_classify_text_phone_allowed():
    assert qc.classify_text([("9:41", 0.9), ("87%", 0.9)], [], phone_ok=True) == []


def test_brand_seen():
    assert qc.brand_seen([("FASC0RA", 0.9)], ["Fascora"])
    assert not qc.brand_seen([("Fascora", 0.2), ("Vital", 0.9)], ["Fascora"])


EXPECTED = [
    {"name": "V01_L06", "keywords": ["hairstylist", "styling", "chair", "salon", "client"]},
    {"name": "V28_L34", "keywords": ["scoop", "powder", "pouch", "kitchen", "counter"]},
    {"name": "V29_L34", "keywords": ["boswellia", "turmeric", "root", "kitchen", "counter"]},
]


def test_propose_match():
    m = qc.propose(qc.title_words("Woman_scooping_powder_in_kitchen_2026101512"), EXPECTED)
    assert m["name"] == "V28_L34"
    assert qc.propose(["Dog", "on", "beach"], EXPECTED)["name"] is None


def test_propose_ambiguous():
    m = qc.propose(["Kitchen", "counter"], EXPECTED)
    assert m["name"] is None and m["why"].startswith("ambiguous")


def test_target_name_takes_b_when_number_used():
    title = ["Woman", "scooping", "powder"]
    assert qc.target_name("V28_L34", title, ".mp4", set()) == "V28_L34_woman-scooping-powder.mp4"
    taken = {"V28_L34_scoop-from-pouch.mp4"}
    assert qc.target_name("V28_L34", title, ".mp4", taken) == "V28b_L34_woman-scooping-powder.mp4"


def test_reject_name_counts_tries(tmp_path):
    (tmp_path / "V20_try1_cape-text.mp4").write_bytes(b"x")
    assert qc.reject_name("Flow_x", "V20", "stray-text", ".mp4", tmp_path) == "V20_try2_stray-text.mp4"
    assert qc.reject_name("Flow_x", None, "stray-text", ".mp4", tmp_path) == "Flow_x.mp4"
    assert qc.reason_slug("duplicate of V20.mp4") == "duplicate-download"


def test_expected_from_vtype():
    vt = {"V1": {"head": 'V1 | Line 6 "x" | VO 41:01 | Flow: 9:16, 4s | use the first 2:22', "dur": "4",
                 "attach": ["R1", "Product"], "text": "SUBJECT: Dana, a hairstylist. SETTING: salon. "
                                                      "ACTION: she scoops powder. CAMERA: wide"}}
    c = qc.expected_from_vtype(vt)["clips"][0]
    assert c["name"] == "V01_L06" and c["length"] == 4.0 and c["use"] == "0:00-2:22"
    assert c["product"] is True and c["phone"] is False
    assert "hairstylist" in c["keywords"] and "scoop" in c["keywords"] and "salon" not in c["keywords"]


# ---------- end to end on tiny generated clips ----------

def _make_clip(path: Path, seconds=4, size="1080x1920", fps=24, color="testsrc="):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{color}size={size}:rate={fps}",
                    "-t", str(seconds), "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_run_dry_then_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(qc, "TMP", tmp_path / "tmp")
    clips = tmp_path / "clips"
    clips.mkdir()
    _make_clip(clips / "Woman_scooping_powder_in_kitchen_202610151230.mp4")
    shutil.copy(clips / "Woman_scooping_powder_in_kitchen_202610151230.mp4",
                clips / "Woman_scooping_powder_in_kitchen_202610151230 (1).mp4")
    _make_clip(clips / "Hairstylist_at_styling_chair_202610151231.mp4", seconds=8)
    _make_clip(clips / "V09_L12_grid-insoles.mp4", color="color=c=red:")
    exp = tmp_path / "expected.json"
    exp.write_text(json.dumps({"width": 1080, "height": 1920, "fps": 24, "clips": [
        {**EXPECTED[0], "length": 4}, {**EXPECTED[1], "length": 4, "use": "0:00-2:00"}, EXPECTED[2]]}))

    rep = qc.run(clips, exp, batch="t1", use_ocr=False)
    by = {r["file"]: r for r in rep["clips"]}
    assert rep["new"] == 3 and "V09_L12_grid-insoles.mp4" not in by
    assert by["Woman_scooping_powder_in_kitchen_202610151230 (1).mp4"]["status"] == "FLAG"
    assert by["Woman_scooping_powder_in_kitchen_202610151230 (1).mp4"]["flags"][0].startswith("duplicate of")
    assert by["Woman_scooping_powder_in_kitchen_202610151230.mp4"]["status"] == "PASS"
    assert by["Woman_scooping_powder_in_kitchen_202610151230.mp4"]["match"]["name"] == "V28_L34"
    hair = by["Hairstylist_at_styling_chair_202610151231.mp4"]
    assert hair["status"] == "FLAG" and hair["flags"][0].startswith("length 8.0s")
    out = tmp_path / "tmp" / "qc" / "t1"
    assert (out / "Woman_scooping_powder_in_kitchen_202610151230_sheet.jpg").exists()
    assert (out / "Woman_scooping_powder_in_kitchen_202610151230_use.jpg").exists()
    assert (out / "report.json").exists()
    assert sorted(p.name for p in clips.iterdir()) == sorted(  # dry run moved nothing
        ["Woman_scooping_powder_in_kitchen_202610151230.mp4", "V09_L12_grid-insoles.mp4",
         "Woman_scooping_powder_in_kitchen_202610151230 (1).mp4", "Hairstylist_at_styling_chair_202610151231.mp4"])
    assert "| PASS |" in qc.table(rep)

    rep = qc.run(clips, exp, batch="t2", apply=True, use_ocr=False)
    names = sorted(p.name for p in clips.iterdir() if p.is_file())
    assert names == ["V09_L12_grid-insoles.mp4", "V28_L34_woman-scooping-powder-in-kitchen.mp4"]
    assert sorted(p.name for p in (clips / "_rejected").iterdir()) == [
        "V01_L06_try1_wrong-length.mp4", "V28_L34_try1_duplicate-download.mp4"]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_run_all_and_ok_override(tmp_path, monkeypatch):
    monkeypatch.setattr(qc, "TMP", tmp_path / "tmp")
    clips = tmp_path / "clips"
    clips.mkdir()
    _make_clip(clips / "V01_L06_on-feet.mp4", seconds=2)
    exp = tmp_path / "expected.json"
    exp.write_text(json.dumps({"clips": [{**EXPECTED[0], "length": 4}]}))
    rep = qc.run(clips, exp, batch="a", include_named=True, use_ocr=False)
    assert rep["clips"][0]["status"] == "FLAG" and rep["clips"][0]["match"]["name"] == "V01_L06"
    rep = qc.run(clips, exp, batch="b", include_named=True, apply=True, ok={"V01_L06_on-feet.mp4"}, use_ocr=False)
    assert rep["clips"][0]["status"] == "PASS"
    assert (clips / "V01_L06_on-feet.mp4").exists()  # named files are never moved
