import subprocess
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from PIL import Image
import sheets


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    p = tmp_path_factory.mktemp("src") / "a.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=576x1024:rate=30:duration=4", "-pix_fmt", "yuv420p", str(p)], check=True)
    return str(p)


def _plan(src, n):
    clips = [{"file": src, "src_in": 0.0, "src_out": 2.0, "at": 2.0 * i, "track": "main", "speed": 1.0}
             for i in range(n)]
    return {"timelines": [{"name": "A", "clips": clips, "overlays": []}]}


def test_tile_labels_and_size(tmp_path, src):
    frames = [(str(i + 1), sheets.grab(src, 1.0, tmp_path / f"f{i}.png")) for i in range(5)]
    out = sheets.tile(frames, tmp_path / "s.png")
    im = Image.open(out).convert("RGB")
    assert im.size == (1080, 1440)
    assert sum(im.getpixel((4, 4))) < 120   # label box is dark


def test_clip_sheets_twelve_per_sheet(tmp_path, src):
    r = sheets.clip_sheets(_plan(src, 14), "A", tmp_path)
    assert [s["items"] for s in r["sheets"]] == [[str(i) for i in range(1, 13)], ["13", "14"]]
    assert all(Path(s["path"]).exists() for s in r["sheets"])


def test_ai_mode_three_cells_per_clip(tmp_path, src):
    r = sheets.clip_sheets(_plan(src, 2), "A", tmp_path, ai=True)
    assert len(r["sheets"]) == 1
    assert r["sheets"][0]["items"] == ["1·in", "1·mid", "1·out", "2·in", "2·mid", "2·out"]


def test_inventory_lists_probe_and_strip(tmp_path, src):
    folder = tmp_path / "raw"; folder.mkdir()
    for n in ("x.mp4", "y.mp4"):
        (folder / n).write_bytes(Path(src).read_bytes())
    r = sheets.inventory(folder, tmp_path / "out")
    assert len(r["clips"]) == 2
    c = r["clips"][0]
    assert c["duration"] == pytest.approx(4.0, abs=0.1) and c["fps"] == 30
    assert Path(c["strip"]).exists()
    assert len(r["sheets"]) == 1


def test_overlay_sheets_without_rendered_file(tmp_path, src):
    plan = _plan(src, 1)
    plan["timelines"][0]["overlays"] = [{"template": "badge", "at": 0.5, "duration": 1.0}]
    r = sheets.overlay_sheets(plan, "A", tmp_path)
    assert r["sheets"][0]["items"] == ["ov1 badge"]


def test_inventory_recurses_case_insensitive_and_labels_relative(tmp_path, src):
    folder = tmp_path / "raw"
    for rel in ("At Work/a.MOV", "At Work/a.mp4", "Flexing/b.MP4", "top.mov", "notes.txt"):
        p = folder / rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(Path(src).read_bytes())
    r = sheets.inventory(folder, tmp_path / "out")
    assert [c["rel"] for c in r["clips"]] == ["At Work/a.MOV", "At Work/a.mp4", "Flexing/b.MP4", "top.mov"]
    assert len({c["strip"] for c in r["clips"]}) == 4   # a.MOV and a.mp4 no longer collide
    assert r["sheets"][0]["items"][0] == "1 At Work/a.MOV"
    assert len(sheets.inventory(folder, tmp_path / "out2", max_clips=2)["clips"]) == 2


def test_inventory_skips_unreadable(tmp_path, src):
    folder = tmp_path / "raw"; folder.mkdir()
    (folder / "good.mp4").write_bytes(Path(src).read_bytes())
    (folder / "bad.mp4").write_bytes(b"not a video")
    r = sheets.inventory(folder, tmp_path / "out")
    assert [c["rel"] for c in r["clips"]] == ["good.mp4"]
    assert [s["rel"] for s in r["skipped"]] == ["bad.mp4"]
