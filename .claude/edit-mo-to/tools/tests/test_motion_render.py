import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import motion_render as mr  # noqa: E402

TPL = """<!--defaults {"text": "Hello", "color": "#fff", "duration": 3} -->
<div data-duration="{{duration}}" style="color:{{color}}">{{text}}</div>"""


def test_fill_uses_defaults_and_overrides():
    html = mr.fill(TPL, {"text": "Hi"})
    assert ">Hi<" in html and "color:#fff" in html and 'data-duration="3"' in html
    assert "defaults" not in html


def test_fill_escapes_html():
    html = mr.fill(TPL, {"text": "<b>R&D</b>"})
    assert "&lt;b&gt;R&amp;D&lt;/b&gt;" in html


def test_fill_rejects_unknown_variable():
    with pytest.raises(ValueError, match="unknown"):
        mr.fill(TPL, {"txt": "typo"})


def test_fill_rejects_placeholder_without_default():
    with pytest.raises(ValueError, match="no default"):
        mr.fill(TPL + "{{missing}}", {})


def test_fill_rejects_bad_duration():
    with pytest.raises(ValueError, match="duration"):
        mr.fill(TPL, {"duration": "abc"})


def test_every_template_has_defaults_and_fills():
    names = mr.list_templates()
    assert {"badge", "cta", "end-card", "hook-number", "word-pop", "stat", "split-labels"} <= set(names)
    for name, info in names.items():
        assert "duration" in info["defaults"], name
        html = mr.fill(mr.template_text(name), {})
        assert "{{" not in html, name
        assert 'data-duration="' in html and "window.__timelines" in html, name


@pytest.mark.slow
def test_render_badge_has_alpha(tmp_path):
    out = tmp_path / "badge.mov"
    info = mr.render("badge", out, {"text": "TEST", "duration": 2})
    assert out.exists() and info["alpha"] is True
    assert abs(info["duration"] - 2) < 0.1
    assert info["width"] == 1080 and info["height"] == 1920


# ---- HyperFrames `check` (lint + runtime + layout + contrast audit) ----

@pytest.mark.slow
def test_check_passes_default_badge():
    rep = mr.check("badge", {"duration": 2})
    assert rep["ok"] is True and rep["errors"] == []


@pytest.mark.slow
def test_check_flags_text_running_off_canvas():
    rep = mr.check("badge", {"text": "THIS BADGE TEXT IS FAR TOO LONG TO FIT ON ANY PHONE SCREEN", "size": 120, "duration": 2})
    codes = {f["code"] for f in rep["errors"] + rep["warnings"] + rep["info"]}
    assert codes & {"canvas_overflow", "text_box_overflow", "container_overflow"}


@pytest.mark.slow
def test_kinetic_title_auto_fits_long_lines():
    rep = mr.check("kinetic-title", {"line1": "ONLY THE R-FORM WORKS", "line2": "ON YOUR NERVES EVERY SINGLE DAY", "duration": 2})
    held = [f for f in rep["errors"] + rep["warnings"] if f["code"] in ("canvas_overflow", "text_box_overflow")]
    assert held == []
    late = [f for f in rep["info"] if f["code"] == "canvas_overflow" and f.get("time", 0) > 0.5]
    assert late == []


def test_stage_media_copies_real_files_only(tmp_path):
    import motion_render as mr

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    work = tmp_path / "work"
    work.mkdir()
    out = mr._stage_media({"video1": str(clip), "video2": "placeholder.mp4", "label1": "BEFORE"}, work)
    assert out == {"video1": "media_video1.mp4", "video2": "placeholder.mp4", "label1": "BEFORE"}
    assert (work / "media_video1.mp4").exists()


def test_stage_media_inlines_svg_without_scripts(tmp_path):
    svg = tmp_path / "logo.svg"
    svg.write_text('<?xml version="1.0"?><!-- c --><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" '
                   'onload="alert(1)"><script>alert(2)</script><path d="M0 0H10V10Z"/></svg>', encoding="utf-8")
    out = mr._stage_media({"svg": str(svg)}, tmp_path)
    assert out["svg"].startswith("<svg") and "<path" in out["svg"]
    assert "script" not in out["svg"] and "onload" not in out["svg"] and "<?xml" not in out["svg"]
    html = mr.fill(mr.template_text("logo-reveal"), out)
    assert "&lt;svg" in html   # escaped into a JS string, decoded by the template


def test_trace_keeps_holes_and_crops_to_the_ink(tmp_path):
    import cv2
    import numpy as np

    img = np.full((300, 600), 255, np.uint8)
    cv2.circle(img, (300, 150), 100, 0, -1)
    cv2.circle(img, (300, 150), 50, 255, -1)          # a ring: one outer shape, one hole
    png = tmp_path / "ring.png"
    cv2.imwrite(str(png), img)
    info = mr.trace(png, tmp_path / "ring.svg")
    text = (tmp_path / "ring.svg").read_text(encoding="utf-8")
    assert info["shapes"] == 2 and 'fill-rule="evenodd"' in text
    w, h = map(float, info["viewbox"].split()[2:])
    assert 200 <= w <= 212 and 200 <= h <= 212
