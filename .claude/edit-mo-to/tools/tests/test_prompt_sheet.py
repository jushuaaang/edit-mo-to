import json
import subprocess
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
import plan_tools as pt
import prompt_sheet as ps
from test_plan_tools_prompts import SCRIPT, SPEC2

TOOL = Path(__file__).resolve().parents[1] / "prompt_sheet.py"


def _spec(tmp_path, spec, name="prompts2.json"):
    d = tmp_path / name.split("/")[0] if "/" in name else tmp_path
    d.mkdir(parents=True, exist_ok=True)
    p = d / Path(name).name
    p.write_text(json.dumps(spec), encoding="utf-8")
    return p


def _board(folder, beats, characters=()):
    (folder / "storyboard").mkdir(parents=True, exist_ok=True)
    (folder / "storyboard" / "storyboard.json").write_text(json.dumps(
        {"title": "T", "characters": list(characters), "beats": beats}), encoding="utf-8")


def _cards(data):
    return [c for g in data["groups"] for c in g["cards"]]


def test_clip_copy_matches_block(tmp_path):
    data = ps.collect(tmp_path, [_spec(tmp_path, SPEC2)], SCRIPT, None)
    cards = _cards(data)
    assert [c["id"] for c in cards] == ["AI-1", "AI-2"]
    for c, p in zip(cards, SPEC2["prompts"]):
        assert c["copy"] == pt._block(SPEC2, p)
    assert cards[0]["line"] == SCRIPT[0] and cards[0]["vo"] == "0:00 – 4:00"


def test_storyboard_cards(tmp_path):
    _board(tmp_path, [{"id": "SB-1", "line": "Hello", "prompt": "keyframe one", "status": "prompt"},
                      {"id": "SB-2", "line": "World", "prompt": None, "status": None}],
           [{"id": "CHAR-1", "name": "Hero", "prompt": "sheet prompt", "status": "prompt"}])
    data = ps.collect(tmp_path, [], [], None)
    assert [c["copy"] for c in data["characters"]] == ["sheet prompt"]
    assert [c["id"] for c in data["keyframes"]] == ["SB-1"]
    assert data["waiting_keyframes"] == ["SB-2"]


def test_storyboard_wins_over_spec_keyframe(tmp_path):
    _board(tmp_path, [{"id": "SB-1", "line": "Hello", "prompt": "edited in GUI", "status": "changed"}])
    spec = dict(SPEC2, prompts=[{"id": "SB-1", "kind": "keyframe", "subject": "old"}] + SPEC2["prompts"])
    data = ps.collect(tmp_path, [_spec(tmp_path, spec)], SCRIPT, None)
    assert [c["copy"] for c in data["keyframes"]] == ["edited in GUI"]


def test_client_rows_only_in_order(tmp_path):
    client = {"id": "C1", "kind": "client", "line": 3, "vo_in_f": 240, "vo_out_f": 300,
              "file": "/v/a.mp4", "in_f": 30, "out_f": 90}
    data = ps.collect(tmp_path, [_spec(tmp_path, dict(SPEC2, prompts=SPEC2["prompts"] + [client]))], SCRIPT, None)
    assert "C1" not in [c["id"] for c in _cards(data)]
    row = [r for r in data["order"] if r["id"] == "C1"][0]
    assert row["client"] and "a.mp4" in row["source"]


def test_two_specs_two_groups(tmp_path):
    a = _spec(tmp_path, dict(SPEC2, job="Nat_T01"), "T01/prompts2.json")
    b = _spec(tmp_path, dict(SPEC2, job="Nat_T02"), "T02/prompts2.json")
    data = ps.collect(tmp_path, [a, b], SCRIPT, None)
    assert [g["title"] for g in data["groups"]] == ["Nat_T01", "Nat_T02"]


def test_script_tag_escaped(tmp_path):
    _board(tmp_path, [{"id": "SB-1", "line": "x", "prompt": "evil </script><b>hi</b>", "status": "prompt"}])
    html = ps.render(ps.collect(tmp_path, [], [], None), "Sheet", "job")
    assert html.count("</script>") == html.count("<script")
    assert "evil </script>" not in html


def test_rewritten_note_chip(tmp_path):
    spec = dict(SPEC2, prompts=[dict(SPEC2["prompts"][0], note="rewritten after a flag")])
    data = ps.collect(tmp_path, [_spec(tmp_path, spec)], SCRIPT, None)
    assert "rewritten after a flag" in _cards(data)[0]["chips"]


def test_setup_folded_and_copy_fallback(tmp_path):
    html = ps.render(ps.collect(tmp_path, [_spec(tmp_path, SPEC2)], SCRIPT, None), "S", "j")
    assert 'execCommand("copy")' in html
    assert '<details class="setup">' in html   # closed by default: prompts come first on screen


def test_nothing_to_show_exits_2(tmp_path):
    r = subprocess.run([sys.executable, str(TOOL), str(tmp_path), "--out", str(tmp_path / "s.html")],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "no prompts" in r.stderr.lower()


def test_cli_writes_html(tmp_path):
    _board(tmp_path, [{"id": "SB-1", "line": "x", "prompt": "kf", "status": "prompt"}])
    out = tmp_path / "s.html"
    r = subprocess.run([sys.executable, str(TOOL), str(tmp_path), "--prompts", str(_spec(tmp_path, SPEC2)),
                        "--out", str(out), "--title", "My sheet"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == str(out)
    html = out.read_text(encoding="utf-8")
    assert "<title>My sheet</title>" in html and "Copy prompt" in html
