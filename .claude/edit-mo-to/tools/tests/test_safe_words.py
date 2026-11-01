"""Task H3: safer wording. safe-words.json lists risky words per group with a plain hint; plan_tools warns (never
errors) on each one found in a video or image prompt, naming the shot; the prompt text itself never changes."""
import copy
import json
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_tools as pt  # noqa: E402
import qa_check  # noqa: E402
from test_plan_tools_prompts import SCRIPT, SPEC2  # noqa: E402

SAFE = TOOLS.parent / "safe-words.json"
GROUPS = ("people", "children", "body", "medical", "violence", "brands")


def test_safe_words_file_shape():
    data = json.loads(SAFE.read_text(encoding="utf-8"))
    assert set(GROUPS) <= set(data["groups"])
    for name, g in data["groups"].items():
        assert g["label"] and g["hint"] and g["words"], name
        assert all(isinstance(w, str) and w.strip() for w in g["words"]), name
        assert len(g["words"]) <= 30, name                     # short and editable
    assert "Describe the action instead of the body" in data["groups"]["body"]["hint"]
    for w in ("bare skin", "skin close-up", "bikini", "undress", "naked", "body shot"):
        assert w in data["groups"]["body"]["words"], w
    for bare in ("skin", "body", "treatment", "minor"):   # fix round 1: phrases, not bare words
        assert all(bare not in g["words"] for g in data["groups"].values()), bare
    for w in ("child", "kid", "baby", "toddler"):
        assert w in data["groups"]["children"]["words"], w
    assert "cure" in data["groups"]["medical"]["words"] and "blood" in data["groups"]["violence"]["words"]


def _spec(**changes):
    s = copy.deepcopy(SPEC2)
    s["prompts"][0].update(changes)
    return s


def test_clean_spec_has_no_wording_warnings():
    assert pt.wording_warnings(SPEC2) == [] and pt.prompt_warnings(SPEC2) == []


def test_risky_words_warn_with_the_shot_and_the_hint():
    s = _spec(action="0.0-4.0s: she rubs cream on her bare skin in a bikini")
    ws = pt.wording_warnings(s)
    assert len(ws) == 2                                        # one per risky phrase ("skin", "bikini")
    assert all(w.startswith("AI clip 1 (AI-1)") for w in ws)
    assert any('"bare skin"' in w for w in ws) and any('"bikini"' in w for w in ws)
    assert all("hand applies cream to the arm" in w for w in ws)
    assert pt.check_prompts(s, SCRIPT, None) == []             # never an error
    assert all(w in pt.prompt_warnings(s) for w in ws)


def test_words_match_whole_words_any_case():
    assert pt.wording_warnings(_spec(subject="woman with a SKINCARE jar")) == []   # not a phrase inside a word
    assert pt.wording_warnings(_spec(subject="her skin glows, body lotion on the shelf")) == []   # plain words are fine
    assert len(pt.wording_warnings(_spec(subject="a Skin Close-Up of her cheek"))) == 1
    assert len(pt.wording_warnings(_spec(subject="Blood orange juice"))) == 1


def test_image_prompts_and_locks_are_checked_once():
    s = copy.deepcopy(SPEC2)
    s["prompts"].append({"id": "SB-3", "kind": "keyframe", "subject": "a toddler holding the bottle",
                         "locks": ["realism", "notext", "look"]})
    s["locks"]["realism"] += " She stands in a bikini."
    ws = pt.wording_warnings(s)
    assert any(w.startswith("Shot 3 (SB-3)") and '"toddler"' in w for w in ws)
    lock = [w for w in ws if "lock" in w.split(":")[0].lower()]
    assert len(lock) == 1 and '"bikini"' in lock[0] and "realism" in lock[0]   # once, not per prompt


def test_negative_and_client_rows_are_not_checked():
    s = _spec(negative="no blood, no weapons, no kids")
    s["prompts"].append({"id": "C-1", "kind": "client", "line": 3, "file": "D:/F/knife.mp4", "in_f": 0, "out_f": 30})
    assert pt.wording_warnings(s) == []


def test_old_prompt_output_is_unchanged_by_the_warnings():
    s = _spec(action="0.0-4.0s: she rubs cream on her skin")
    before = pt.render_prompts(s, SCRIPT, None)
    assert "she rubs cream on her skin" in before                # nothing is rewritten by the tool


def test_cli_warns_and_still_passes(tmp_path):
    spec = tmp_path / "prompts2.json"
    spec.write_text(json.dumps(_spec(action="0.0-4.0s: a famous celebrity lifts the bottle")), encoding="utf-8")
    script = tmp_path / "script.txt"
    script.write_text("\n".join(SCRIPT), encoding="utf-8")
    r = subprocess.run([sys.executable, str(TOOLS / "plan_tools.py"), "check-prompts", str(spec), "--script", str(script)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True and out["errors"] == []
    assert any('"celebrity"' in w for w in out["warnings"])
    assert "warning: AI clip 1 (AI-1)" in r.stderr


def test_qa_shows_wording_as_its_own_open_row():
    s = _spec(action="0.0-4.0s: she says it cures everything")
    res = qa_check.check_prompts_rows(s, SCRIPT, None)
    rows = [r for r in res["rows"] if r["check"] == "safe_wording"]
    assert rows and all(r["status"] == "OPEN" for r in rows)
    assert not [r for r in res["rows"] if r["check"] == "generator_limits" and "cure" in r["evidence"]]
    assert res["verdict"] == "PASS" and "safe_wording" in qa_check.OPEN_CHECKS


def _shared_lock_lines() -> list[str]:
    """The lock lines of the shared preferences.md ("Repeat the locks in every prompt" and its sub-bullets)."""
    lines = (TOOLS.parent / "preferences.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if "Repeat the locks" in l)
    out = [lines[start]]
    for l in lines[start + 1:]:
        if not l.startswith("  "):
            break
        out.append(l)
    return out


def test_shared_preference_locks_do_not_warn():
    """Fix round 1: today's preferences.md locks (Realism "Skin keeps its true tone…", Look "skin tone…") are what
    every live-footage job uses, so they must not trip a warning."""
    locks = _shared_lock_lines()
    assert any("Skin keeps its true" in l for l in locks) and any("Look lock" in l for l in locks)
    spec = copy.deepcopy(SPEC2)
    spec["locks"] = {f"l{i}": l for i, l in enumerate(locks)}
    for p in spec["prompts"]:
        p["locks"] = list(spec["locks"])
    assert pt.wording_warnings(spec) == []


def test_a_real_risky_phrase_still_warns():
    for text, word in (("close shot of her bare skin", "bare skin"), ("she starts to undress", "undress"),
                       ("a toddler eats cereal", "toddler"), ("this serum cures acne", "cures")):
        ws = pt.wording_warnings(_spec(action=text))
        assert len(ws) == 1 and f'"{word}"' in ws[0], (text, ws)
