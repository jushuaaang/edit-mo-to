import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import learn as lr  # noqa: E402

PREFS = "# starter\n\n## General\n- Follow the brief.\n\n## B-roll\n- Mostly client B-roll.\n\n## Music\n- Duck music under VO.\n"


def root_with_prefs(tmp_path):
    (tmp_path / "preferences.md").write_text(PREFS, encoding="utf-8")
    return tmp_path


def test_known_rule_is_dropped_even_with_different_numbers_and_tags():
    existing = ["- B-roll: cuts about 0:12 shorter than the VO span [Zapply 2026-10-15]"]
    assert lr.is_known("B-roll: cut about 0:09 shorter than the VO span", existing)
    assert lr.is_known("Music: duck 6 dB under the VO", existing) is None


def test_normalise_numbers_tags_punctuation_stop_words():
    n = lr.normalise("Cut 0:12 of the clip [Zapply 2026-10-15]!")
    assert "#" in n and "the" not in n and "zapply" not in n and "clip" in n
    assert all(w.isalnum() or w == "#" for w in n)


def test_existing_rules_reads_all_sources(tmp_path):
    root = root_with_prefs(tmp_path)
    (root / "my-preferences.md").write_text("## B-roll\n- Mine one.\nnot a bullet\n", encoding="utf-8")
    (root / "clients").mkdir()
    (root / "clients" / "zapply.md").write_text("- Client rule.\n", encoding="utf-8")
    lr.decline("Declined rule", root)
    got = lr.existing_rules(root)
    for want in ("Follow the brief.", "Mine one.", "Client rule.", "Declined rule"):
        assert any(want in g for g in got)
    assert not any("not a bullet" in g for g in got)


def test_declined_rules_are_never_proposed_again(tmp_path):
    root = root_with_prefs(tmp_path)
    lr.decline("Music: fade out over the last 2 seconds", root)
    out = lr.propose([], ["Music: fade out over the last 3 seconds", "Totally new rule about zoom"], root)
    assert [d["rule"] for d in out["dropped"]] == ["Music: fade out over the last 3 seconds"]
    assert out["dropped"][0]["matches"] == ["Music: fade out over the last 2 seconds"]
    assert [p["rule"] for p in out["proposals"]] == ["Totally new rule about zoom"]
    assert (root / "learning-declined.jsonl").exists()


def test_propose_drops_rule_already_in_preferences(tmp_path):
    root = root_with_prefs(tmp_path)
    out = lr.propose([], ["Duck music under the VO"], root)
    assert out["proposals"] == [] and len(out["dropped"]) == 1


def test_candidates_from_recurring_patterns_and_notes():
    pats = [
        {"id": "b-roll:shorter", "text": "Shortened 3 of 6 b-roll clips, by 0:12 on average", "count": 3},
        {"id": "overlay:removed", "text": "Deleted 1 of 4 overlay items", "count": 1},
        {"id": "music:quieter", "text": "Made music quieter by 4.0 dB (1 clips)", "count": 1, "recurring": True},
    ]
    out = lr.candidates(pats, ["Keep CTA on screen to the end"])
    rules = {c["rule"]: c for c in out}
    broll = rules["B-roll: cut about 0:12 shorter than the VO span"]
    assert broll["section"] == "B-roll" and broll["why"] == pats[0]["text"]
    assert len([c for c in out if c["section"] == "B-roll"]) == 1
    assert not any("overlay" in c["rule"].lower() for c in out)  # count 1, not recurring: skipped
    assert any(c["why"] == pats[2]["text"] for c in out)  # recurring entry kept despite count 1
    note = rules["Keep CTA on screen to the end"]
    assert note["why"] == "Keep CTA on screen to the end"


def test_save_creates_my_preferences_with_sections(tmp_path):
    root = root_with_prefs(tmp_path)
    p = lr.save("B-roll: cut shorter", "B-roll", root)
    assert p == root / "my-preferences.md"
    text = p.read_text(encoding="utf-8")
    heads = [l for l in text.splitlines() if l.startswith("## ")]
    assert heads == ["## General", "## B-roll", "## Music"]
    broll = text.split("## B-roll")[1].split("## Music")[0]
    assert "- B-roll: cut shorter" in broll
    lr.save("Second", "B-roll", root)
    assert (root / "my-preferences.md").read_text(encoding="utf-8").count("- Second") == 1


def test_save_unknown_section_and_client(tmp_path):
    root = root_with_prefs(tmp_path)
    lr.save("New thing", "Brand new", root)
    assert "## Brand new\n- New thing" in (root / "my-preferences.md").read_text(encoding="utf-8")
    c = lr.save("Client only", "B-roll", root, client="zapply")
    assert c == root / "clients" / "zapply.md" and "- Client only" in c.read_text(encoding="utf-8")


def test_cli_propose_and_decline(tmp_path, capsys):
    root = root_with_prefs(tmp_path)
    d = tmp_path / "diff.json"
    d.write_text(json.dumps({"patterns": [{"id": "b-roll:shorter",
                                           "text": "Shortened 3 of 6 b-roll clips, by 0:12 on average", "count": 3}]}))
    n = tmp_path / "notes.txt"
    n.write_text("A note rule\n\n")
    lr.main(["propose", "--patterns", str(d), "--notes", str(n), "--root", str(root)])
    out = json.loads(capsys.readouterr().out)
    assert len(out["proposals"]) == 2
    lr.main(["decline", "A note rule", "--root", str(root)])
    capsys.readouterr()
    lr.main(["propose", "--patterns", str(d), "--notes", str(n), "--root", str(root)])
    out = json.loads(capsys.readouterr().out)
    assert len(out["proposals"]) == 1 and out["dropped"][0]["rule"] == "A note rule"
