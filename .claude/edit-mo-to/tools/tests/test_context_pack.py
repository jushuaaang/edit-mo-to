import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import context_pack as cp  # noqa: E402

PREFS = """# Preferences
intro text

## General
general rule
## Prompts (all generators)
prompt rule
## Google Flow
flow rule
## Higgsfield · Seedance
higgsfield seedance rule
## Seedance
seedance rule
## UGC
ugc rule
## B-roll
broll rule
## Pixar
pixar rule
## Editing in CapCut
editing rule
## Captions
caption rule
## Known generation failures (prevent in prompts)
failure rule
"""


def _root(tmp_path, mine=None, client=None):
    d = tmp_path / ".claude" / "edit-mo-to"
    (d / "clients").mkdir(parents=True)
    (d / "preferences.md").write_text(PREFS, encoding="utf-8")
    if mine:
        (d / "my-preferences.md").write_text(mine, encoding="utf-8")
    if client:
        (d / "clients" / "acme.md").write_text(client, encoding="utf-8")
    return tmp_path


def test_pack_has_general_style_generator_and_failures_only(tmp_path):
    pack = cp.build_pack("broll", generator="google-flow", root=_root(tmp_path))
    for s in ("## General", "## B-roll", "## Google Flow", "## Known generation failures", "## Prompts (all generators)", "## Editing in CapCut"):
        assert s in pack
    for s in ("## UGC", "## Pixar", "Seedance", "Higgsfield", "intro text"):
        assert s not in pack


def test_pack_adds_editor_rules_and_client(tmp_path):
    root = _root(tmp_path, mine="## General\nmy general\n## UGC\nmy ugc\n## B-roll\nmy broll\n", client="acme notes\n")
    pack = cp.build_pack("broll", client="acme", root=root)
    i_mine, i_client = pack.index("# Editor's own rules (win on conflict)"), pack.index("# Client")
    assert pack.index("failure rule") < i_mine < i_client
    assert "my general" in pack and "my broll" in pack and "my ugc" not in pack
    assert "acme notes" in pack


def test_pack_has_captions_after_editing(tmp_path):
    root = _root(tmp_path, mine="## Captions\nmy caption look\n")
    pack = cp.build_pack("ugc", root=root)
    assert pack.index("## Editing in CapCut") < pack.index("## Captions") < pack.index("## Known generation failures")
    assert "caption rule" in pack and "my caption look" in pack


def test_pack_without_optional_files(tmp_path):
    pack = cp.build_pack("ugc", generator="seedance", root=_root(tmp_path))
    assert "Editor's own rules" not in pack and "# Client" not in pack
    assert "## Seedance" in pack and "## UGC" in pack


def test_pack_names_the_higgsfield_model_and_its_limits(tmp_path):
    pack = cp.build_pack("ugc", generator="higgsfield", model="kling-3.0", root=_root(tmp_path))
    assert "Higgsfield · Kling 3.0" in pack
    assert "not verified" in pack and "generators.json" in pack
    assert "seedance rule" not in pack and "## Google Flow" not in pack


def test_pack_for_a_seedance_model_has_the_higgsfield_seedance_rules(tmp_path):
    root = _root(tmp_path, mine="## Seedance\nmy seedance\n")
    pack = cp.build_pack("pixar", generator="higgsfield", model="seedance-2.5", root=root)
    assert "## Higgsfield · Seedance" in pack and "Higgsfield · Seedance 2.5" in pack
    assert "my seedance" in pack   # an editor's own "Seedance" section applies to the Seedance models
    assert "Start on @Image1." in pack


def test_pack_generator_aliases_and_cli(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(cp, "ROOT", root)
    out = tmp_path / "pack.md"
    cp.main(["ugc", "--generator", "seedance", "--out", str(out)])       # old name still accepted
    assert "Higgsfield · Seedance 2.0" in out.read_text(encoding="utf-8")
    cp.main(["ugc", "--generator", "higgsfield", "--model", "kling-3.0", "--out", str(out)])
    assert "Higgsfield · Kling 3.0" in out.read_text(encoding="utf-8")
    cp.main(["ugc", "--generator", "flow", "--out", str(out)])
    assert "## Google Flow" in out.read_text(encoding="utf-8")


def test_pack_names_the_flow_model_and_its_limits(tmp_path):
    pack = cp.build_pack("broll", generator="google-flow", model="veo-3.1-fast", root=_root(tmp_path))
    assert "Google Flow · Veo 3.1 Fast" in pack and "## Google Flow" in pack
    assert "4, 6, 8" in pack and "not verified" in pack
    assert "Higgsfield" not in pack
    plain = cp.build_pack("broll", generator="google-flow", root=_root(tmp_path / "b"))
    assert "## Generator: Google Flow (from generators.json)" in plain and "4–8 s" in plain


def test_pack_cli_takes_model_for_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "ROOT", _root(tmp_path))
    out = tmp_path / "pack.md"
    cp.main(["broll", "--generator", "flow", "--model", "quality", "--out", str(out)])
    assert "Google Flow · Veo 3.1 Quality" in out.read_text(encoding="utf-8")
