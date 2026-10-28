import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storyboard as sb  # noqa: E402


def _clip(path: Path):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x568:d=2:r=30",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


def test_sheet_mixes_client_frames_keyframes_and_cards(tmp_path):
    clip = tmp_path / "clip.mp4"
    _clip(clip)
    out = tmp_path / "storyboard"
    out.mkdir()
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=540x960",
                    "-frames:v", "1", str(out / "SB-2.png")], check=True)
    data = {"title": "Test & <Co>", "direction": "Open on the pain.", "font": "Inter", "bg": "#0e2f5a",
            "beats": [{"id": "SB-1", "line": "It's here", "est": "0:00–1:20", "shot": {"type": "client", "file": str(clip), "t": 1}},
                      {"id": "SB-2", "line": "Morning", "est": "1:20–3:00", "shot": {"type": "ai", "framing": "Wide"}},
                      {"id": "SB-3", "line": "Heel", "est": "3:00–4:10",
                       "shot": {"type": "ai", "framing": "Close-up", "subject": "a heel"}, "transition": "whip"}]}
    res = sb.build(data, out, render_graphics=False)
    assert res["panels"] == 3 and res["keyframes_missing"] == ["SB-3"]
    page = Path(res["html"]).read_text(encoding="utf-8")
    assert page.count("data:image/jpeg;base64,") == 3  # self-contained: every panel embedded
    assert "Test &amp; &lt;Co&gt;" in page and "It&#x27;s here" in page  # text is escaped
    assert "AI · SHOT CARD" in page and "AI · KEYFRAME" in page and "CLIENT" in page
    assert not list(out.glob("*_base.png"))  # work files never land in the video folder


def test_old_storyboard_output_unchanged(tmp_path):
    """The GUI's fields (characters; per beat prompt, status, visual) never change the share page."""
    import copy
    import re

    clip = tmp_path / "clip.mp4"
    _clip(clip)
    old = {"title": "Test", "direction": "Open on the pain.", "font": "Inter", "bg": "#0e2f5a",
           "beats": [{"id": "SB-1", "line": "It's here", "est": "0:00–1:20", "shot": {"type": "client", "file": str(clip), "t": 1}},
                     {"id": "SB-2", "line": "Morning", "est": "1:20–3:00", "shot": {"type": "ai", "framing": "Wide"}},
                     {"id": "SB-3", "line": "Heel", "est": "3:00–4:10",
                      "shot": {"type": "ai", "framing": "Close-up", "subject": "a heel"}, "transition": "whip"}]}
    new = copy.deepcopy(old)
    new["characters"] = [{"id": "CHAR-1", "name": "Sofía <host>", "prompt": "Character sheet, 4 views", "status": "image"}]
    for beat, prompt, status in zip(new["beats"], [None, "Wide shot, morning light", None], [None, "prompt", "changed"]):
        beat.update(prompt=prompt, status=status, visual="warm, <b>bright</b>")

    pages = []
    for name, data in (("old", old), ("new", new)):
        out = tmp_path / name
        out.mkdir()
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=540x960",
                        "-frames:v", "1", str(out / "SB-2.png")], check=True)
        (out / "CHAR-1.png").write_bytes((out / "SB-2.png").read_bytes())
        res = sb.build(data, out, render_graphics=False)
        assert res["keyframes_missing"] == ["SB-3"] and res["panels"] == 3
        pages.append(re.sub(r"base64,[A-Za-z0-9+/=]+", "base64,", Path(res["html"]).read_text(encoding="utf-8")))
    assert pages[0] == pages[1]
    assert "CHAR-1" not in pages[1] and "Sofía" not in pages[1] and "bright" not in pages[1]
