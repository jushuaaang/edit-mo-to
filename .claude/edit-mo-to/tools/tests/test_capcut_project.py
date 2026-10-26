import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capcut_project as cp  # noqa: E402
from machine import PATHS, TMP  # noqa: E402

API = "http://localhost:9001"
DRAFT_CACHE = TMP / "_test_fixture"


def _media(rel: str, lavfi: list) -> str:
    """The real sample file under root if this PC has it, else a synthetic stand-in with the same name, made once with ffmpeg."""
    real = Path(PATHS["root"]) / rel
    if real.exists():
        return real.as_posix()
    out = TMP / "_test_media" / rel
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *lavfi, str(out)], check=True)
    return out.as_posix()


CLIP = _media("zapply/edited/hook2.mp4",
              ["-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=6",
               "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-shortest", "-pix_fmt", "yuv420p"])


def _api_up():
    try:
        requests.post(f"{API}/create_draft", json={"width": 1080, "height": 1920}, timeout=3)
        return True
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def base_draft():
    """A real single-timeline VectCutAPI draft, built once and cached."""
    if (DRAFT_CACHE / "draft_info.json").exists():
        return DRAFT_CACHE
    if not _api_up():
        pytest.skip("VectCutAPI not running on :9001")
    r = requests.post(f"{API}/create_draft", json={"width": 1080, "height": 1920}).json()
    did = r["output"]["draft_id"]
    requests.post(f"{API}/add_video", json={"draft_id": did, "video_url": CLIP, "start": 0, "end": 4, "target_start": 0})
    requests.post(f"{API}/save_draft", json={"draft_id": did, "draft_folder": str(DRAFT_CACHE.parent)})
    folder = cp.wait_for_draft(DRAFT_CACHE.parent / did, timeout_s=30)
    if DRAFT_CACHE.exists():
        shutil.rmtree(DRAFT_CACHE)
    folder.rename(DRAFT_CACHE)
    return DRAFT_CACHE


AUDIO_CACHE = TMP / "_test_audio_fixture"
AUDIO = _media("for cloning.MP3",
               ["-f", "lavfi", "-i", "sine=frequency=330:duration=8"])


@pytest.fixture(scope="session")
def audio_draft():
    """A VectCutAPI draft holding only one audio track (music/VO to merge into a timeline)."""
    if (AUDIO_CACHE / "draft_info.json").exists():
        return AUDIO_CACHE
    if not _api_up():
        pytest.skip("VectCutAPI not running on :9001")
    did = requests.post(f"{API}/create_draft", json={"width": 1080, "height": 1920}).json()["output"]["draft_id"]
    requests.post(f"{API}/add_audio", json={"draft_id": did, "audio_url": AUDIO, "start": 0, "end": 5,
                                            "target_start": 0, "volume": 0.1, "track_name": "music"})
    requests.post(f"{API}/save_draft", json={"draft_id": did, "draft_folder": str(AUDIO_CACHE.parent), "auto_deploy": False})
    folder = cp.wait_for_draft(AUDIO_CACHE.parent / did, timeout_s=30)
    if AUDIO_CACHE.exists():
        shutil.rmtree(AUDIO_CACHE)
    folder.rename(AUDIO_CACHE)
    return AUDIO_CACHE


@pytest.fixture(autouse=True)
def capcut_closed(monkeypatch):
    """Tests run while the user's CapCut may be open; pretend it's closed unless a test says otherwise."""
    monkeypatch.setattr(cp, "_capcut_running", lambda: False)


@pytest.fixture
def drafts(base_draft, tmp_path):
    """Two independent copies of the base draft, as if built separately."""
    out = []
    for n in ("a", "b"):
        d = tmp_path / f"src_{n}"
        shutil.copytree(base_draft, d)
        out.append(d)
    return out


def _just_edited(path: Path):
    """Like touch, but always later than our own last write (touch can land in the same clock tick)."""
    t = time.time() + 1
    os.utime(path, (t, t))


def _old(path: Path):
    t = time.time() - 60
    os.utime(path, (t, t))


def _all_paths(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "path" and isinstance(v, str) and v:
                yield v
            else:
                yield from _all_paths(v)
    elif isinstance(o, list):
        for v in o:
            yield from _all_paths(v)


def _composed(tmp_path, drafts):
    target = tmp_path / "Proj One"
    cp.compose(target, [("Timeline 01 - Body+CTA", drafts[0]), ("Timeline 02 - Hook 1", drafts[1])])
    _old(target / "draft_info.json")
    return target


def test_compose_assigns_unique_timeline_ids(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    pj = json.loads((target / "Timelines" / "project.json").read_text(encoding="utf-8"))
    ids = [t["id"] for t in pj["timelines"]]
    assert len(set(ids)) == 2
    for i in ids:
        assert (target / "Timelines" / i / "draft_info.json").exists()
        assert (target / "Timelines" / i / "draft_content.json").exists()


def test_compose_rewrites_all_paths_to_existing_files(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    for f in (target / "Timelines").glob("*/draft_info.json"):
        paths = list(_all_paths(json.loads(f.read_text(encoding="utf-8"))))
        media = [p for p in paths if "/assets/" in p.replace("\\", "/")]
        assert media
        for p in media:
            assert Path(p).exists(), p
            assert Path(p).resolve().is_relative_to(target.resolve())


def test_compose_sets_main_timeline(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    pj = json.loads((target / "Timelines" / "project.json").read_text(encoding="utf-8"))
    assert pj["main_timeline_id"] == pj["timelines"][0]["id"]
    root = json.loads((target / "draft_info.json").read_text(encoding="utf-8"))
    main = json.loads((target / "Timelines" / pj["main_timeline_id"] / "draft_info.json").read_text(encoding="utf-8"))
    assert root == main
    meta = json.loads((target / "draft_meta_info.json").read_text(encoding="utf-8"))
    assert meta["draft_name"] == "Proj One"


def test_compose_refuses_existing_target(tmp_path, drafts):
    target = tmp_path / "Exists"
    target.mkdir()
    with pytest.raises(FileExistsError):
        cp.compose(target, [("T1", drafts[0])])


def test_add_timeline_appends_and_keeps_existing(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    before = {f: f.read_bytes() for f in (target / "Timelines").glob("*/draft_info.json")}
    third = tmp_path / "src_c"
    shutil.copytree(base_draft, third)
    res = cp.add_timeline(target, "Timeline 03 - Hook 2", third)
    names = [t["name"] for t in cp.list_timelines(target)]
    assert names == ["Timeline 01 - Body+CTA", "Timeline 02 - Hook 1", "Timeline 03 - Hook 2"]
    for f, data in before.items():
        assert f.read_bytes() == data
    assert (target / "Timelines" / res["id"] / "draft_info.json").exists()


def test_add_timeline_converts_single_timeline_project(tmp_path, drafts):
    single = tmp_path / "Single"
    shutil.copytree(drafts[0], single)
    _old(single / "draft_info.json")
    cp.add_timeline(single, "Timeline 02 - Hook 1", drafts[1])
    names = [t["name"] for t in cp.list_timelines(single)]
    assert names == ["Timeline 01", "Timeline 02 - Hook 1"]
    for f in (single / "Timelines").glob("*/draft_info.json"):
        for p in _all_paths(json.loads(f.read_text(encoding="utf-8"))):
            if "/assets/" in p.replace("\\", "/"):
                assert Path(p).exists(), p


def test_duplicate_timeline_copies_content_with_new_id(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    res = cp.duplicate_timeline(target, "Timeline 02 - Hook 1", "Timeline 03 - Hook 1 rev 1")
    tls = cp.list_timelines(target)
    src = next(t for t in tls if t["name"] == "Timeline 02 - Hook 1")
    assert res["id"] != src["id"]
    a = json.loads((target / "Timelines" / src["id"] / "draft_info.json").read_text(encoding="utf-8"))
    b = json.loads((target / "Timelines" / res["id"] / "draft_info.json").read_text(encoding="utf-8"))
    assert b["id"] == res["id"]
    a.pop("id"), b.pop("id")
    assert a == b


def test_backup_timeline_creates_bak_folder(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    bak = cp.backup_timeline(target, "Timeline 01 - Body+CTA")
    assert bak.exists() and ".bak-" in bak.name
    assert (bak / "draft_info.json").exists()
    assert len(cp.list_timelines(target)) == 2  # backup is not a timeline


def test_add_timeline_refuses_recently_modified(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    _just_edited(target / "draft_info.json")
    with pytest.raises(cp.ProjectBusy):
        cp.add_timeline(target, "X", drafts[0])


def test_replace_timeline_backs_up_and_keeps_id(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    main = next(t for t in cp.list_timelines(target) if t["main"])
    new_src = tmp_path / "src_new"
    shutil.copytree(base_draft, new_src)
    c = json.loads((new_src / "draft_info.json").read_text(encoding="utf-8"))
    c["duration"] = 123456
    (new_src / "draft_info.json").write_text(json.dumps(c), encoding="utf-8")
    res = cp.replace_timeline(target, main["name"], new_src)
    assert Path(res["backup"]).exists()
    for f in [target / "Timelines" / main["id"] / n for n in cp.CONTENT_FILES] + [target / "draft_info.json"]:
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["id"] == main["id"] and d["duration"] == 123456
        for p in _all_paths(d):
            if "/assets/" in p.replace("\\", "/"):
                assert Path(p).exists(), p
    assert [t["id"] for t in cp.list_timelines(target)] == [t["id"] for t in cp.list_timelines(target)]


def test_own_writes_do_not_count_as_busy(tmp_path, drafts, base_draft):
    target = tmp_path / "Back To Back"
    cp.compose(target, [("T1", drafts[0])])  # no aging: our own fresh write
    cp.add_timeline(target, "T2", drafts[1])
    cp.duplicate_timeline(target, "T2", "T3")
    assert [t["name"] for t in cp.list_timelines(target)] == ["T1", "T2", "T3"]


def _timeline_json(project, name):
    tid = next(t["id"] for t in cp.list_timelines(project) if t["name"] == name)
    return json.loads((project / "Timelines" / tid / "draft_info.json").read_text(encoding="utf-8"))


def test_add_tracks_merges_audio_and_keeps_existing_edits(tmp_path, drafts, audio_draft):
    target = _composed(tmp_path, drafts)
    before = _timeline_json(target, "Timeline 02 - Hook 1")
    seg_track = next(i for i, t in enumerate(before["tracks"]) if t["segments"])
    before["tracks"][seg_track]["segments"][0]["volume"] = 0.42  # simulate a hand edit (e.g. captions, levels)
    tid = next(t["id"] for t in cp.list_timelines(target) if t["name"] == "Timeline 02 - Hook 1")
    for n in cp.CONTENT_FILES:
        (target / "Timelines" / tid / n).write_text(json.dumps(before), encoding="utf-8")
    cp._mark_own_write(target)
    res = cp.add_tracks(target, "Timeline 02 - Hook 1", audio_draft, track_type="audio")
    after = _timeline_json(target, "Timeline 02 - Hook 1")
    assert after["tracks"][seg_track]["segments"][0]["volume"] == 0.42
    assert len(after["tracks"]) == len(before["tracks"]) + 1
    assert after["tracks"][-1]["type"] == "audio"
    seg_mat = after["tracks"][-1]["segments"][0]["material_id"]
    audios = {m["id"]: m for m in after["materials"]["audios"]}
    assert seg_mat in audios and Path(audios[seg_mat]["path"]).exists()
    assert Path(res["backup"]).exists()


def test_rewrite_leaves_external_paths_alone(tmp_path, drafts):
    single = tmp_path / "Hand Edited"
    shutil.copytree(drafts[0], single)
    c = json.loads((single / "draft_info.json").read_text(encoding="utf-8"))
    c["materials"]["videos"][0]["path"] = "D:/Video Editing/Nativia/assets/raw clip.mp4"
    (single / "draft_info.json").write_text(json.dumps(c), encoding="utf-8")
    _old(single / "draft_info.json")
    cp.add_timeline(single, "T2", drafts[1])
    root = json.loads((single / "draft_info.json").read_text(encoding="utf-8"))
    assert root["materials"]["videos"][0]["path"] == "D:/Video Editing/Nativia/assets/raw clip.mp4"


def test_duplicate_timeline_names_refused(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    with pytest.raises(ValueError):
        cp.add_timeline(target, "Timeline 02 - Hook 1", drafts[0])
    with pytest.raises(ValueError):
        cp.duplicate_timeline(target, "Timeline 02 - Hook 1", "Timeline 01 - Body+CTA")
    with pytest.raises(ValueError):
        cp.compose(tmp_path / "Dupes", [("A", drafts[0]), ("A", drafts[1])])


def test_failed_compose_leaves_nothing(tmp_path, drafts):
    target = tmp_path / "Partial"
    with pytest.raises(FileNotFoundError):
        cp.compose(target, [("A", drafts[0]), ("B", tmp_path / "missing")])
    assert not target.exists()
    assert not any(p.name.startswith("Partial") for p in tmp_path.iterdir())


def test_busy_when_capcut_running(tmp_path, drafts, monkeypatch):
    target = _composed(tmp_path, drafts)
    monkeypatch.setattr(cp, "_capcut_running", lambda: True)
    with pytest.raises(cp.ProjectBusy):
        cp.add_timeline(target, "T3", drafts[0])


def test_busy_when_a_timeline_file_was_just_edited(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    tid = cp.list_timelines(target)[1]["id"]
    _just_edited(target / "Timelines" / tid / "draft_info.json")
    with pytest.raises(cp.ProjectBusy):
        cp.add_timeline(target, "T3", drafts[0])


def test_segments_lists_original_files(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    segs = cp.segments(target, "Timeline 01 - Body+CTA")["segments"]
    assert segs and segs[0]["track_type"] == "video"
    assert segs[0]["source"].replace("\\", "/").endswith("zapply/edited/hook2.mp4")
    assert segs[0]["at"] == 0.0 and segs[0]["duration"] > 0


def test_unsafe_project_name_refused(tmp_path, drafts):
    with pytest.raises(ValueError):
        cp.compose(tmp_path / "Bad:Name", [("A", drafts[0])])


def test_wait_for_draft_raises_on_missing(tmp_path):
    with pytest.raises(cp.DraftSaveFailed):
        cp.wait_for_draft(tmp_path / "nope", timeout_s=0.5)


def _capcut_saves(project, name, edit):
    """Simulate CapCut 9.6 saving a timeline: it rewrites draft_content.json only, so
    draft_info.json goes stale (seen on the Zapply rehearsal, 2026-10-15)."""
    tid = next(t["id"] for t in cp.list_timelines(project) if t["name"] == name)
    folder = project / "Timelines" / tid
    _old(folder / "draft_info.json")
    c = json.loads((folder / "draft_content.json").read_text(encoding="utf-8"))
    edit(c)
    (folder / "draft_content.json").write_text(json.dumps(c), encoding="utf-8")
    _old(folder / "draft_content.json")  # CapCut quit a while ago, so the project isn't busy
    os.utime(folder / "draft_info.json", (time.time() - 120, time.time() - 120))
    return folder


def _add_caption_track(c):
    c.setdefault("materials", {}).setdefault("texts", []).append({"id": "CAPTION-1", "content": "auto caption"})
    c["tracks"].append({"type": "text", "name": "captions", "segments": [
        {"material_id": "CAPTION-1", "target_timerange": {"start": 0, "duration": 1_000_000}}]})


def test_add_tracks_keeps_captions_capcut_saved_in_draft_content(tmp_path, drafts, audio_draft):
    target = _composed(tmp_path, drafts)
    folder = _capcut_saves(target, "Timeline 02 - Hook 1", _add_caption_track)
    cp.add_tracks(target, "Timeline 02 - Hook 1", audio_draft, track_type="audio")
    for n in cp.CONTENT_FILES:
        c = json.loads((folder / n).read_text(encoding="utf-8"))
        types = [t["type"] for t in c["tracks"]]
        assert "text" in types and types[-1] == "audio", (n, types)
        assert any(m["id"] == "CAPTION-1" for m in c["materials"]["texts"])


def test_add_tracks_on_main_timeline_updates_both_root_files(tmp_path, drafts, audio_draft):
    target = _composed(tmp_path, drafts)
    _capcut_saves(target, "Timeline 01 - Body+CTA", _add_caption_track)
    cp.add_tracks(target, "Timeline 01 - Body+CTA", audio_draft, track_type="audio")
    for n in cp.CONTENT_FILES:
        types = [t["type"] for t in json.loads((target / n).read_text(encoding="utf-8"))["tracks"]]
        assert "text" in types and types[-1] == "audio", (n, types)


def test_segments_sees_capcut_saved_edits(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    _capcut_saves(target, "Timeline 02 - Hook 1", _add_caption_track)
    assert any(s["track_type"] == "text" for s in cp.segments(target, "Timeline 02 - Hook 1")["segments"])


# --- Zapply rehearsal follow-ups (2026-10-15) ---

PLACEHOLDER = "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"


def _to_capcut_form(project, c):
    """What CapCut 9.6 does on save: project-local paths become placeholders and remote_url is dropped."""
    for key, items in c.get("materials", {}).items():
        for m in items if isinstance(items, list) else []:
            if isinstance(m, dict) and isinstance(m.get("path"), str) and m["path"].startswith(project.as_posix()):
                m["path"] = PLACEHOLDER + m["path"][len(project.as_posix()):]
                m.pop("remote_url", None)


def _strip_remote_urls_everywhere(project):
    for f in [f for n in cp.CONTENT_FILES for f in project.rglob(n)]:
        c = json.loads(f.read_text(encoding="utf-8"))
        _to_capcut_form(project, c)
        f.write_text(json.dumps(c), encoding="utf-8")
        _old(f)


def test_main_without_project_prints_usage():
    for argv in (["list"], ["segments", "only-project"], ["add-tracks", "p", "n"], []):
        with pytest.raises(SystemExit) as e:
            cp.main(argv)
        assert "CLI" in str(e.value.code), argv


def test_segments_reports_layout_text_and_duration(tmp_path, drafts):
    target = _composed(tmp_path, drafts)

    def edit(c):
        _to_capcut_form(target, c)
        vid = next(t for t in c["tracks"] if t["type"] == "video" and t["segments"])["segments"][0]
        vid["clip"]["transform"] = {"x": 0.0, "y": 0.5}
        vid["clip"]["scale"] = {"x": 1.2, "y": 1.2}
        vid["clip"]["rotation"] = 90.0
        c["materials"]["videos"][0]["crop"] = {"upper_left_x": 0.1, "upper_left_y": 0.0, "upper_right_x": 0.9,
                                               "upper_right_y": 0.0, "lower_left_x": 0.1, "lower_left_y": 1.0,
                                               "lower_right_x": 0.9, "lower_right_y": 1.0}
        c["materials"].setdefault("common_mask", []).append(
            {"id": "MASK-1", "type": "mask", "name": "Rectangle", "config": {"width": 1.0, "height": 0.5}})
        vid.setdefault("extra_material_refs", []).append("MASK-1")
        c["materials"].setdefault("texts", []).append(
            {"id": "CAPTION-1", "content": json.dumps({"text": "that's what happens", "styles": []})})
        c["tracks"].append({"type": "text", "name": "captions", "segments": [
            {"material_id": "CAPTION-1", "target_timerange": {"start": 0, "duration": 1_000_000}}]})
        c["duration"] = 4_500_000

    _capcut_saves(target, "Timeline 01 - Body+CTA", edit)
    out = cp.segments(target, "Timeline 01 - Body+CTA")
    assert out["duration"] == 4.5
    vid = next(s for s in out["segments"] if s["track_type"] == "video")
    assert vid["transform"] == {"x": 0.0, "y": 0.5}
    assert vid["scale"] == {"x": 1.2, "y": 1.2}
    assert vid["rotation"] == 90.0
    assert vid["crop"]["upper_left_x"] == 0.1
    assert vid["mask"] == [{"name": "Rectangle", "config": {"width": 1.0, "height": 0.5}}]
    assert vid["path"].startswith(PLACEHOLDER)
    assert vid["remote_url"] is None
    # remote_url is gone from this timeline, but draft_info.json of another timeline still knows it
    assert vid["source"].replace("\\", "/").endswith("zapply/edited/hook2.mp4")
    txt = next(s for s in out["segments"] if s["track_type"] == "text")
    assert txt["text"] == "that's what happens"


def test_segments_untouched_clip_has_no_crop_or_mask(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    vid = cp.segments(target, "Timeline 02 - Hook 1")["segments"][0]
    assert vid["crop"] is None and vid["mask"] == []
    assert vid["remote_url"].replace("\\", "/").endswith("zapply/edited/hook2.mp4")
    assert Path(vid["path"]).exists()


def test_segments_maps_placeholder_by_vectcut_hash(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    _strip_remote_urls_everywhere(target)  # nothing in the project remembers the source any more
    seg = cp.segments(target, "Timeline 01 - Body+CTA")["segments"][0]
    assert seg["source"].startswith(PLACEHOLDER)  # unknown without a folder to search
    seg = cp.segments(target, "Timeline 01 - Body+CTA", search_dirs=[Path(CLIP).parent])["segments"][0]
    assert seg["source"].replace("\\", "/").endswith("zapply/edited/hook2.mp4")


def test_add_tracks_uses_projects_placeholder_paths(tmp_path, drafts, audio_draft):
    target = _composed(tmp_path, drafts)
    _capcut_saves(target, "Timeline 02 - Hook 1", lambda c: _to_capcut_form(target, c))
    cp.add_tracks(target, "Timeline 02 - Hook 1", audio_draft, track_type="audio")
    after = _timeline_json(target, "Timeline 02 - Hook 1")
    music = after["tracks"][-1]["segments"][0]["material_id"]
    mat = next(m for m in after["materials"]["audios"] if m["id"] == music)
    assert mat["path"].startswith(PLACEHOLDER + "/assets/"), mat["path"]
    assert (target / mat["path"][len(PLACEHOLDER) + 1:]).exists()
    assert mat["remote_url"]  # keep the original for segments/QA


def test_add_tracks_keeps_absolute_paths_when_project_has_no_placeholder(tmp_path, drafts, audio_draft):
    target = _composed(tmp_path, drafts)
    cp.add_tracks(target, "Timeline 02 - Hook 1", audio_draft, track_type="audio")
    after = _timeline_json(target, "Timeline 02 - Hook 1")
    music = after["tracks"][-1]["segments"][0]["material_id"]
    assert Path(next(m for m in after["materials"]["audios"] if m["id"] == music)["path"]).exists()


def _fake_probe(rotation):
    def probe(path):
        return (3840, 2160, rotation)
    return probe


def _landscape_draft(src):
    c = json.loads((src / "draft_info.json").read_text(encoding="utf-8"))
    c["materials"]["videos"][0].update(width=3840, height=2160)
    (src / "draft_info.json").write_text(json.dumps(c), encoding="utf-8")


def test_compose_stores_rotated_phone_clips_upright(tmp_path, drafts, monkeypatch):
    """CapCut 9.6 stores a -90 rotated .MOV at its upright size (2160x3840, clip rotation 0);
    VectCutAPI stores the coded landscape size. Match CapCut."""
    _landscape_draft(drafts[0])
    monkeypatch.setattr(cp, "_probe_video", _fake_probe(-90))
    res = cp.compose(tmp_path / "Rot", [("T1", drafts[0])])
    v = _timeline_json(tmp_path / "Rot", "T1")["materials"]["videos"][0]
    assert (v["width"], v["height"]) == (2160, 3840)
    assert cp.segments(tmp_path / "Rot", "T1")["segments"][0]["size"] == "2160x3840"
    assert res["rotation_fixed"] and res["rotation_fixed"][0]["rotation"] == -90


def test_compose_leaves_180_rotation_alone(tmp_path, drafts, monkeypatch):
    _landscape_draft(drafts[0])
    monkeypatch.setattr(cp, "_probe_video", _fake_probe(-180))
    res = cp.compose(tmp_path / "Rot180", [("T1", drafts[0])])
    v = _timeline_json(tmp_path / "Rot180", "T1")["materials"]["videos"][0]
    assert (v["width"], v["height"]) == (3840, 2160)
    assert res["rotation_fixed"] == []


def test_unprobeable_clip_is_flagged(tmp_path, drafts, monkeypatch):
    monkeypatch.setattr(cp, "_probe_video", lambda path: None)
    res = cp.add_timeline(_composed(tmp_path, drafts), "T3", drafts[0])
    assert res["rotation_unchecked"]


# --- add-overlay (2026-10-16): add B-roll to a captioned timeline without replace ---

def _shifted_draft(tmp_path, base_draft, start_us):
    """The base draft with its clip moved to start_us on the timeline (a one-clip B-roll draft)."""
    d = tmp_path / f"broll_{start_us}"
    shutil.copytree(base_draft, d)
    for n in cp.CONTENT_FILES:
        if (d / n).exists():
            c = json.loads((d / n).read_text(encoding="utf-8"))
            for t in c["tracks"]:
                for s in t["segments"]:
                    s["target_timerange"]["start"] = start_us
            (d / n).write_text(json.dumps(c), encoding="utf-8")
    return d


def _capcut_style_caption(c):
    """A caption the way CapCut writes it: compact JSON and a float repr Python would print differently."""
    _add_caption_track(c)
    c["materials"]["texts"][-1]["original_size_width"] = 569.8757934570313


def _save_compact(folder):
    raw = (folder / "draft_content.json").read_text(encoding="utf-8")
    raw = json.dumps(json.loads(raw), separators=(",", ":")).replace("569.8757934570312", "569.8757934570313")
    (folder / "draft_content.json").write_text(raw, encoding="utf-8")
    _old(folder / "draft_content.json")
    os.utime(folder / "draft_info.json", (time.time() - 120, time.time() - 120))
    return raw


def test_add_overlay_adds_clip_and_keeps_captions_byte_for_byte(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    folder = _capcut_saves(target, "Timeline 02 - Hook 1", _capcut_style_caption)
    before_raw = _save_compact(folder)
    before = json.loads(before_raw)
    res = cp.add_overlay(target, "Timeline 02 - Hook 1", _shifted_draft(tmp_path, base_draft, 5_000_000), "video_main")
    after_raw = (folder / "draft_content.json").read_text(encoding="utf-8")
    after = json.loads(after_raw)
    caption = next(t for t in before["tracks"] if t["type"] == "text")
    assert json.dumps(caption, separators=(",", ":")) in after_raw  # captions untouched
    assert '"original_size_width":569.8757934570313' in after_raw  # CapCut's float digits kept
    main = next(t for t in after["tracks"] if t.get("name") == "video_main")
    assert [s["target_timerange"]["start"] for s in main["segments"]] == [0, 5_000_000]
    new = main["segments"][1]
    mats = {m["id"]: k for k, v in after["materials"].items() if isinstance(v, list) for m in v}
    assert mats[new["material_id"]] == "videos"
    assert all(r in mats for r in new["extra_material_refs"])
    assert new["id"] != main["segments"][0]["id"]
    assert not set(new["extra_material_refs"]) & set(main["segments"][0]["extra_material_refs"])
    assert after["duration"] == 9_000_000 and res["duration_changed"]
    assert Path(res["backup"]).exists()
    # draft_info.json gets the same content and stays older, so the newest-file read finds the captions
    assert json.loads((folder / "draft_info.json").read_text(encoding="utf-8")) == after
    assert cp._content_file(folder).name == "draft_content.json"
    assert (folder / "draft_info.json").stat().st_mtime < (folder / "draft_content.json").stat().st_mtime


def test_add_overlay_on_main_timeline_updates_root(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    _capcut_saves(target, "Timeline 01 - Body+CTA", _add_caption_track)
    cp.add_overlay(target, "Timeline 01 - Body+CTA", _shifted_draft(tmp_path, base_draft, 4_000_000), "video_main")
    for n in cp.CONTENT_FILES:
        c = json.loads((target / n).read_text(encoding="utf-8"))
        assert "text" in [t["type"] for t in c["tracks"]], n
        main = next(t for t in c["tracks"] if t.get("name") == "video_main")
        assert len(main["segments"]) == 2, n
    assert (target / "draft_info.json").stat().st_mtime < (target / "draft_content.json").stat().st_mtime


def test_add_overlay_refuses_overlap_and_changes_nothing(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    folder = _capcut_saves(target, "Timeline 02 - Hook 1", _add_caption_track)
    before = (folder / "draft_content.json").read_bytes()
    with pytest.raises(ValueError, match="overlap"):
        cp.add_overlay(target, "Timeline 02 - Hook 1", _shifted_draft(tmp_path, base_draft, 2_000_000), "video_main")
    assert (folder / "draft_content.json").read_bytes() == before
    assert not [p for p in (target / cp.BACKUP_DIR).iterdir() if not p.name.endswith(".last.json")]  # no backup made


def test_add_overlay_refuses_missing_track(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    with pytest.raises(ValueError, match="video_overlay"):
        cp.add_overlay(target, "Timeline 02 - Hook 1", _shifted_draft(tmp_path, base_draft, 5_000_000))


def test_add_overlay_refuses_while_capcut_running(tmp_path, drafts, base_draft, monkeypatch):
    target = _composed(tmp_path, drafts)
    monkeypatch.setattr(cp, "_capcut_running", lambda: True)
    with pytest.raises(cp.ProjectBusy):
        cp.add_overlay(target, "Timeline 02 - Hook 1", _shifted_draft(tmp_path, base_draft, 5_000_000), "video_main")


def test_exact_json_round_trips_capcut_floats():
    raw = '{"a":569.8757934570313,"b":[1.0,-0.0,1e-05],"c":"\u00e9/x"}'
    assert cp._dump_exact(cp._read_exact_text(raw)) == raw


# ---- import into CapCut's media panel + timeline uses the imported originals (2026-10-16) ----

def _meta_imports(project):
    meta = json.loads((project / "draft_meta_info.json").read_text(encoding="utf-8"))
    groups = [g for g in meta.get("draft_materials", []) if g.get("type") == 0]
    return groups[0]["value"] if groups else []


def test_import_media_lists_files_once_with_real_names(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    tone = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=2", str(tone)], check=True)
    AUDIO = tone.as_posix()
    res = cp.import_media(target, [CLIP, AUDIO])
    res2 = cp.import_media(target, [CLIP])
    items = _meta_imports(target)
    paths = [i["file_Path"] for i in items]
    assert paths.count(CLIP) == 1 and paths.count(AUDIO) == 1
    v = next(i for i in items if i["file_Path"] == CLIP)
    a = next(i for i in items if i["file_Path"] == AUDIO)
    assert v["metetype"] == "video" and v["extra_info"] == "hook2.mp4" and v["duration"] > 0 and v["width"] > 0
    assert a["metetype"] == "music" and a["duration"] > 0
    assert len(res["added"]) == 2 and res2["added"] == []


def test_link_originals_points_timelines_at_imported_files(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    res = cp.link_originals(target)
    imported = {i["file_Path"] for i in _meta_imports(target)}
    for f in list((target / "Timelines").glob("*/draft_*.json")) + [target / "draft_info.json"]:
        for v in json.loads(f.read_text(encoding="utf-8"))["materials"]["videos"]:
            assert v["path"] == CLIP, f
            assert v["material_name"] == "hook2.mp4"
    assert CLIP in imported
    assert res["relinked"] >= 2 and not any((target / "assets").rglob("*.mp4"))  # hashed copies removed


def test_link_originals_keeps_copy_when_original_missing(tmp_path, drafts):
    target = _composed(tmp_path, drafts)
    f = next((target / "Timelines").glob("*/draft_info.json"))
    c = json.loads(f.read_text(encoding="utf-8"))
    c["materials"]["videos"][0]["remote_url"] = "D:/nope/missing.mp4"
    copy_path = c["materials"]["videos"][0]["path"]
    f.write_text(json.dumps(c), encoding="utf-8")
    _old(f)
    cp._mark_own_write(target)
    cp.link_originals(target)
    c2 = json.loads(f.read_text(encoding="utf-8"))
    assert c2["materials"]["videos"][0]["path"] == copy_path and Path(copy_path).exists()


def test_compose_can_link_originals(tmp_path, drafts):
    target = tmp_path / "Linked"
    cp.compose(target, [("T1", drafts[0])], link_originals=True)
    v = json.loads((target / "draft_info.json").read_text(encoding="utf-8"))["materials"]["videos"][0]
    assert v["path"] == CLIP and CLIP in {i["file_Path"] for i in _meta_imports(target)}


def test_replace_writes_last_snapshot(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    main = next(t for t in cp.list_timelines(target) if t["main"])
    assert cp.last_path(target, main["name"]).exists()  # compose snapshots every timeline
    new_src = tmp_path / "src_new"
    shutil.copytree(base_draft, new_src)
    c = json.loads((new_src / "draft_info.json").read_text(encoding="utf-8"))
    c["duration"] = 123456
    (new_src / "draft_info.json").write_text(json.dumps(c), encoding="utf-8")
    cp.replace_timeline(target, main["name"], new_src)
    last = cp.last_path(target, main["name"])
    assert last == target / cp.BACKUP_DIR / f"{main['name']}.last.json"
    snap = json.loads(last.read_text(encoding="utf-8"))
    assert snap == cp.segments(target, main["name"]) and snap["duration"] == pytest.approx(0.123456)


def test_add_timeline_and_add_tracks_write_last_snapshot(tmp_path, drafts, base_draft, audio_draft):
    target = _composed(tmp_path, drafts)
    src = tmp_path / "src_c"
    shutil.copytree(base_draft, src)
    cp.add_timeline(target, "Timeline 03", src)
    assert json.loads(cp.last_path(target, "Timeline 03").read_text(encoding="utf-8")) == cp.segments(target, "Timeline 03")
    _old(target / "draft_info.json")
    cp.add_tracks(target, "Timeline 03", audio_draft, "audio")
    snap = json.loads(cp.last_path(target, "Timeline 03").read_text(encoding="utf-8"))
    assert snap == cp.segments(target, "Timeline 03") and any(s["track_type"] == "audio" for s in snap["segments"])


def _text_draft(base_draft, tmp_path, track_name="TEMP_EN_delete_me", render_index=15000):
    """A draft (copy of the base draft) whose only track of interest is a text track of two segments."""
    d = tmp_path / f"src_text_{track_name}"
    shutil.copytree(base_draft, d)
    for n in cp.CONTENT_FILES:
        f = d / n
        if not f.exists():
            continue
        c = json.loads(f.read_text(encoding="utf-8"))
        c["tracks"] = [{"type": "text", "name": track_name, "render_index": render_index, "segments": [
            {"id": f"S-{track_name}-{i}", "material_id": f"T-{track_name}-{i}", "extra_material_refs": [],
             "target_timerange": {"start": i * 1_000_000, "duration": 1_000_000}} for i in range(2)]}]
        c.setdefault("materials", {})["texts"] = [
            {"id": f"T-{track_name}-{i}", "content": json.dumps({"text": f"line {i}", "styles": []})} for i in range(2)]
        f.write_text(json.dumps(c), encoding="utf-8")
    return d


def test_add_tracks_text_merges_text_materials(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    text_draft = _text_draft(base_draft, tmp_path)
    res = cp.add_tracks(target, "Timeline 02 - Hook 1", text_draft, track_type="text")
    assert res["tracks_added"] == 1
    after = _timeline_json(target, "Timeline 02 - Hook 1")
    assert after["tracks"][-1]["type"] == "text" and after["tracks"][-1]["name"] == "TEMP_EN_delete_me"
    assert {m["id"] for m in after["materials"]["texts"]} >= {"T-TEMP_EN_delete_me-0", "T-TEMP_EN_delete_me-1"}
    segs = [s for s in cp.segments(target, "Timeline 02 - Hook 1")["segments"] if s["track"] == "TEMP_EN_delete_me"]
    assert [s["text"] for s in segs] == ["line 0", "line 1"]


def test_add_tracks_refuses_duplicate_track_name(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    text_draft = _text_draft(base_draft, tmp_path)
    cp.add_tracks(target, "Timeline 02 - Hook 1", text_draft, track_type="text")
    with pytest.raises(ValueError, match="already on timeline"):
        cp.add_tracks(target, "Timeline 02 - Hook 1", text_draft, track_type="text")
    after = _timeline_json(target, "Timeline 02 - Hook 1")
    assert [t["name"] for t in after["tracks"]].count("TEMP_EN_delete_me") == 1


def test_add_tracks_on_top_raises_render_index_above_existing(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    cp.add_tracks(target, "Timeline 02 - Hook 1", _text_draft(base_draft, tmp_path, "first"), track_type="text")
    cp.add_tracks(target, "Timeline 02 - Hook 1", _text_draft(base_draft, tmp_path, "second"), track_type="text",
                  on_top=True)
    ri = {t["name"]: t.get("render_index") for t in _timeline_json(target, "Timeline 02 - Hook 1")["tracks"]
          if t["type"] == "text"}
    assert ri["first"] == 15000 and ri["second"] > 15000


def test_raise_text_track_puts_it_on_top(tmp_path, drafts, base_draft):
    target = _composed(tmp_path, drafts)
    cp.add_tracks(target, "Timeline 02 - Hook 1", _text_draft(base_draft, tmp_path, "TEMP_EN_delete_me"), track_type="text")
    cp.add_tracks(target, "Timeline 02 - Hook 1", _text_draft(base_draft, tmp_path, "captions"), track_type="text")
    res = cp.raise_text_track(target, "Timeline 02 - Hook 1", "TEMP_EN_delete_me")
    ri = {t["name"]: t["render_index"] for t in _timeline_json(target, "Timeline 02 - Hook 1")["tracks"]
          if t["type"] == "text"}
    assert ri["TEMP_EN_delete_me"] == 15001 and ri["captions"] == 15000
    assert Path(res["backup"]).exists()
    with pytest.raises(ValueError):
        cp.raise_text_track(target, "Timeline 02 - Hook 1", "nope")
