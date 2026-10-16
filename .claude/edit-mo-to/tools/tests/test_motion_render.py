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
