"""Task H3: Gemini Omni Flash, and the model Claude picks (prefs `avoid_models` / `default_model`, per computer)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import generators as gens  # noqa: E402

OMNI = "google-flow:gemini-omni-flash"
VEOS = ["higgsfield:veo-3.1", "google-flow:veo-3.1-fast", "google-flow:veo-3.1-quality", "google-flow:veo-3.1-lite"]


@pytest.mark.parametrize("name", ["gemini-omni-flash", "Gemini Omni Flash", "omni flash", "omniflash", "omni-flash",
                                  "gemini omni flash", "OMNI FLASH"])
def test_omni_flash_resolves_and_is_not_verified(name):
    r = gens.rules("google-flow", name)
    assert r["model"] == "gemini-omni-flash" and r["label"] == "Google Flow · Gemini Omni Flash"
    assert (r["min_s"], r["max_s"], r["max_attach"]) == (4, 8, 7)        # Flow's own site limits, until confirmed
    assert r["start_frame"] is True and r["start_line"] is None
    assert r["verified"] is None and "not verified" in r["warning"]
    assert gens.rules("flow", "omniflash")["model"] == "gemini-omni-flash"


def test_omni_flash_does_not_move_the_higgsfield_fallback():
    assert gens.strictest() == {"min_s": 5, "max_s": 8, "max_attach": 3}


def test_model_ids_cover_every_row():
    ids = gens.model_ids()
    assert OMNI in ids and all(v in ids for v in VEOS)
    assert "higgsfield:seedance-2.0" in ids and len(ids) == len(set(ids))
    t = gens.load()
    assert len(ids) == sum(len(s.get("models", {})) for s in t["generators"].values())


def test_pick_uses_the_default_when_not_avoided():
    prefs = {"avoid_models": VEOS, "default_model": OMNI}
    assert gens.pick_model(prefs) == OMNI
    assert gens.pick_model(prefs, "google-flow") == OMNI
    assert gens.pick_model(prefs, "flow") == OMNI                     # a site alias works too
    assert gens.pick_model(prefs, "higgsfield") == "higgsfield:seedance-2.0"   # another site: its first allowed model


def test_pick_skips_an_avoided_default_and_falls_back_on_the_site():
    prefs = {"avoid_models": [OMNI, "google-flow:veo-3.1-fast"], "default_model": OMNI}
    assert gens.pick_model(prefs) == "google-flow:veo-3.1-quality"    # the default's site, first one not avoided
    assert gens.pick_model({"avoid_models": [], "default_model": None}) == gens.model_ids()[0]
    assert gens.pick_model({}, "google-flow") == "google-flow:veo-3.1-fast"   # no prefs: the site's first row


def test_pick_never_returns_an_avoided_model():
    ids = gens.model_ids()
    for i, avoid_n in enumerate(range(len(ids))):
        avoid = ids[:avoid_n] + ids[avoid_n + 1:][: i % 3]
        for default in [None, *ids]:
            for site in (None, "higgsfield", "google-flow"):
                got = gens.pick_model({"avoid_models": avoid, "default_model": default}, site)
                assert got not in avoid
                if got is not None and site:
                    assert got.startswith(site + ":")
    assert gens.pick_model({"avoid_models": ids}) is None                      # everything avoided: nothing to pick
    flow = [i for i in ids if i.startswith("google-flow:")]
    assert gens.pick_model({"avoid_models": flow, "default_model": None}, "google-flow") is None
    assert gens.pick_model({"avoid_models": flow, "default_model": OMNI}).startswith("higgsfield:")  # site None: any site


def test_pick_ignores_unknown_ids_and_unknown_sites():
    assert gens.pick_model({"avoid_models": ["nope:x"], "default_model": "nope:x"}) == gens.model_ids()[0]
    with pytest.raises(ValueError):
        gens.pick_model({}, "midjourney")


def test_read_prefs_missing_broken_and_unknown(tmp_path):
    f = tmp_path / "gui" / "prefs.json"
    assert gens.read_prefs(f) == {"avoid_models": [], "default_model": None}       # missing file
    f.parent.mkdir()
    f.write_text("not json", encoding="utf-8")
    assert gens.read_prefs(f) == {"avoid_models": [], "default_model": None}
    f.write_text(json.dumps({"sound": False, "avoid_models": [*VEOS, "x:y", 3], "default_model": OMNI}), encoding="utf-8")
    assert gens.read_prefs(f) == {"avoid_models": VEOS, "default_model": OMNI}     # only known ids


def test_pick_reads_the_gui_prefs_file(tmp_path, monkeypatch):
    monkeypatch.setenv("EDIT_MO_TO_GUI_TMP", str(tmp_path))
    assert gens.prefs_file() == tmp_path / "gui" / "prefs.json"
    assert gens.pick_model() == gens.model_ids()[0]                                  # no prefs: no avoid list, no default
    (tmp_path / "gui").mkdir()
    (tmp_path / "gui" / "prefs.json").write_text(json.dumps({"avoid_models": VEOS, "default_model": OMNI}), encoding="utf-8")
    assert gens.pick_model() == OMNI


def _cli(tmp_path, *args):
    env = {"EDIT_MO_TO_GUI_TMP": str(tmp_path), "PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(TOOLS / "generators.py"), *args], capture_output=True, text=True, env=env)


def test_pick_cli(tmp_path):
    (tmp_path / "gui").mkdir()
    (tmp_path / "gui" / "prefs.json").write_text(json.dumps({"avoid_models": VEOS, "default_model": OMNI}), encoding="utf-8")
    r = _cli(tmp_path, "pick")
    assert r.returncode == 0 and r.stdout.strip() == OMNI
    r = _cli(tmp_path, "pick", "--site", "higgsfield")
    assert r.returncode == 0 and r.stdout.strip() == "higgsfield:seedance-2.0"
    (tmp_path / "gui" / "prefs.json").write_text(json.dumps({"avoid_models": gens.model_ids()}), encoding="utf-8")
    r = _cli(tmp_path, "pick")
    assert r.returncode == 1 and "avoid" in r.stderr
    assert _cli(tmp_path, "pick", "--site", "nowhere").returncode == 2
