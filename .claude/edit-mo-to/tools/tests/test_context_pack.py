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
    for s in ("## UGC", "## Pixar", "## Seedance", "intro text"):
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
