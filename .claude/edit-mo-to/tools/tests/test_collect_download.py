"""Task G: tools/collect_download.py copies the newest matching download into the job's target path (Generate for me:
a picture or clip Claude downloaded from Google Flow). It refuses any target outside the video folder."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import collect_download as cd  # noqa: E402


@pytest.fixture
def env(tmp_path):
    folder = tmp_path / "Video A"
    (folder / ".edit-mo-to").mkdir(parents=True)
    (folder / ".edit-mo-to" / "job.json").write_text("{}", encoding="utf-8")
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    return folder, downloads


def _dl(downloads, name, data=b"data", age=0.0):
    p = downloads / name
    p.write_bytes(data)
    t = time.time() - age
    os.utime(p, (t, t))
    return p


def _run(argv, capsys):
    code = 0
    try:
        cd.main(argv)
    except SystemExit as e:
        code = e.code or 0
    return code, json.loads(capsys.readouterr().out)


def test_copies_the_newest_image_into_storyboard(env, capsys):
    folder, downloads = env
    _dl(downloads, "older.png", b"old", age=60)
    _dl(downloads, "flow_image.png", b"new", age=1)
    _dl(downloads, "clip.mp4", b"video", age=0)          # newest, but not a picture
    code, out = _run([str(folder), "storyboard/SB-5.png", "--downloads", str(downloads)], capsys)
    assert code == 0, out
    dest = folder / "storyboard" / "SB-5.png"
    assert out == {"ok": True, "path": dest.resolve().as_posix(), "from": "flow_image.png"}
    assert dest.read_bytes() == b"new"
    assert (downloads / "flow_image.png").exists()        # a copy: the download stays


def test_keeps_the_downloaded_extension(env, capsys):
    folder, downloads = env
    _dl(downloads, "flow.jpg", b"jpg")
    code, out = _run([str(folder), "storyboard/SB-2.png", "--downloads", str(downloads)], capsys)
    assert code == 0 and out["path"].endswith("/storyboard/SB-2.jpg")


def test_clip_into_the_clips_folder(env, capsys):
    folder, downloads = env
    _dl(downloads, "flow_video.mp4", b"mp4")
    _dl(downloads, "partial.mp4.crdownload", b"x", age=-5)   # still downloading: never picked
    _dl(downloads, ".hidden.mp4", b"x", age=-5)
    code, out = _run([str(folder), str(folder / "clips" / "V01_L02.mp4"), "--downloads", str(downloads)], capsys)
    assert code == 0 and out["from"] == "flow_video.mp4"
    assert (folder / "clips" / "V01_L02.mp4").read_bytes() == b"mp4"


def test_only_recent_downloads(env, capsys):
    folder, downloads = env
    _dl(downloads, "old.png", age=3 * 3600)
    code, out = _run([str(folder), "storyboard/SB-1.png", "--downloads", str(downloads)], capsys)
    assert code == 1 and "no new" in out["error"]
    code, out = _run([str(folder), "storyboard/SB-1.png", "--downloads", str(downloads), "--within", "240"], capsys)
    assert code == 0


def test_never_overwrites_without_replace(env, capsys):
    folder, downloads = env
    (folder / "storyboard").mkdir()
    (folder / "storyboard" / "SB-1.jpg").write_bytes(b"mine")
    _dl(downloads, "new.png", b"new")
    code, out = _run([str(folder), "storyboard/SB-1.png", "--downloads", str(downloads)], capsys)
    assert code == 1 and (folder / "storyboard" / "SB-1.jpg").read_bytes() == b"mine"
    code, out = _run([str(folder), "storyboard/SB-1.png", "--downloads", str(downloads), "--replace"], capsys)
    assert code == 0 and (folder / "storyboard" / "SB-1.png").read_bytes() == b"new"
    assert not (folder / "storyboard" / "SB-1.jpg").exists()     # a replaced keyframe keeps a single file


@pytest.mark.parametrize("target", ["../outside.png", "/tmp/x.png", ".edit-mo-to/x.png", "storyboard/../../x.png",
                                    "storyboard/SB-1.exe", "storyboard/"])
def test_refuses_targets_outside_the_video_folder(env, capsys, target):
    folder, downloads = env
    _dl(downloads, "a.png")
    code, out = _run([str(folder), target, "--downloads", str(downloads)], capsys)
    assert code == 1 and out["ok"] is False
    assert not (folder.parent / "outside.png").exists() and not (folder.parent / "x.png").exists()


def test_refuses_a_folder_without_a_job(tmp_path, capsys):
    folder, downloads = tmp_path / "Plain", tmp_path / "Downloads"
    folder.mkdir()
    downloads.mkdir()
    _dl(downloads, "a.png")
    code, out = _run([str(folder), "storyboard/SB-1.png", "--downloads", str(downloads)], capsys)
    assert code == 1


def test_a_symlinked_subfolder_cannot_lead_out(env, capsys, tmp_path):
    folder, downloads = env
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (folder / "storyboard").symlink_to(elsewhere, target_is_directory=True)
    _dl(downloads, "a.png")
    code, _ = _run([str(folder), "storyboard/SB-1.png", "--downloads", str(downloads)], capsys)
    assert code == 1 and not list(elsewhere.iterdir())


# --- Task G fix: a planted .part symlink, targets checked where they really land ---

def test_a_planted_part_symlink_cannot_write_outside(env, capsys, tmp_path):
    folder, downloads = env
    outside = tmp_path / "outside"
    outside.mkdir()
    (folder / "storyboard").mkdir()
    (folder / "storyboard" / ".SB-1.png.part").symlink_to(outside / "pwn.png")
    _dl(downloads, "a.png", b"img")
    code, out = _run([str(folder), "storyboard/SB-1.png", "--downloads", str(downloads)], capsys)
    dest = folder / "storyboard" / "SB-1.png"
    assert not (outside / "pwn.png").exists() and not list(outside.iterdir())
    assert code == 0 and dest.is_file() and not dest.is_symlink() and dest.read_bytes() == b"img"
    assert not (folder / "storyboard" / ".SB-1.png.part").exists() and not (folder / "storyboard" / ".SB-1.png.part").is_symlink()


def test_open_new_refuses_a_file_that_appears(tmp_path):
    part = tmp_path / ".x.part"
    with cd.open_new(part) as f:
        f.write(b"1")
    with pytest.raises(FileExistsError):   # O_EXCL: a second open while it exists fails (open_new removes only before)
        os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL)


def test_a_symlinked_subfolder_into_edit_mo_to_is_refused(env, capsys):
    folder, downloads = env
    (folder / "storyboard").symlink_to(folder / ".edit-mo-to", target_is_directory=True)
    _dl(downloads, "a.png")
    code, out = _run([str(folder), "storyboard/x.png", "--downloads", str(downloads)], capsys)
    assert code == 1 and ".edit-mo-to" in out["error"]
    assert not (folder / ".edit-mo-to" / "x.png").exists()


@pytest.mark.parametrize("target", ["x.png", "other/x.png", "storyboard2/x.png"])
def test_only_the_allowed_subfolders(env, capsys, target):
    folder, downloads = env
    _dl(downloads, "a.png")
    code, out = _run([str(folder), target, "--downloads", str(downloads)], capsys)
    assert code == 1 and "storyboard/" in out["error"]
    assert not (folder / target).exists()


def test_the_cards_own_clips_folder_is_allowed(env, capsys):
    folder, downloads = env
    (folder / ".edit-mo-to" / "job.json").write_text(json.dumps({"card": {"clips_folder": "My Clips"}}), encoding="utf-8")
    _dl(downloads, "a.mp4", b"v")
    code, out = _run([str(folder), "My Clips/V01.mp4", "--downloads", str(downloads)], capsys)
    assert code == 0 and (folder / "My Clips" / "V01.mp4").read_bytes() == b"v"
