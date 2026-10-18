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
