import json
import subprocess
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_tools as pt

SCRIPT = ["Meet Nativia, the vitamin I never skip.", "Two capsules every morning and I feel it.",
          "Link in my bio, go try it."]
SPEC2 = {
    "style": "ugc", "mode": "flow", "generator": "google-flow", "product": "Nativia", "aspect": "9:16",
    "attach": {"@Image1": "refs/R1_headshot.png", "@Image2": "refs/product.png"},
    "locks": {
        "realism": "REALISM LOCK: shot on a phone, natural light, no studio polish.",
        "product": "PRODUCT LOCK: the Nativia bottle, white label, green cap, never altered.",
        "notext": "NO TEXT LOCK: no captions, subtitles or watermarks anywhere in frame.",
        "voice": "VOICE LOCK: same female voice, warm, mid pace, American accent.",
        "look": "LOOK LOCK: bright bathroom, soft warm key, shallow depth of field.",
        "pacing": "PACING LOCK: speak at a natural pace, no pauses over half a second.",
    },
    "prompts": [
        {"id": "AI-1", "line": 1, "vo_in_f": 0, "vo_out_f": 120, "gen_len_s": 4, "setting": "bathroom mirror",
         "subject": "young woman holding the bottle", "action": "0.0-4.0s: she smiles and lifts the bottle",
         "camera": "selfie, handheld", "dialogue": "Meet Nativia, the vitamin I never skip.",
         "attach": ["@Image1", "@Image2"], "locks": ["realism", "product", "notext", "voice", "look", "pacing"],
         "negative": "no extra people"},
        {"id": "AI-2", "line": 2, "vo_in_f": 120, "vo_out_f": 240, "gen_len_s": 4, "setting": "kitchen",
         "subject": "same woman pouring capsules", "action": "0.0-4.0s: she taps two capsules into her hand",
         "camera": "selfie, handheld", "dialogue": "Two capsules every morning and I feel it.",
         "attach": ["@Image1", "@Image2"], "locks": ["realism", "product", "notext", "voice", "look", "pacing"],
         "lock_overrides": {"product": "PRODUCT LOCK OVERRIDE: the open Nativia tub, scoop visible."},
         "negative": "no extra people"},
    ],
}


def test_locks_are_expanded_in_full_in_every_prompt():
    out = pt.render_prompts(SPEC2, SCRIPT, None)
    assert out.count(SPEC2["locks"]["realism"]) == 2 and "```" in out and "| AI-1 (generate) |" in out


def test_lock_override_replaces_only_that_lock():
    out = pt.render_prompts(SPEC2, SCRIPT, None)
    blocks = out.split("```")[1::2]
    assert len(blocks) == 2
    assert SPEC2["locks"]["product"] in blocks[0] and "OVERRIDE" not in blocks[0]
    assert "PRODUCT LOCK OVERRIDE" in blocks[1] and SPEC2["locks"]["product"] not in blocks[1]
    assert SPEC2["locks"]["realism"] in blocks[1]


def test_check_clean_spec_passes():
    assert pt.check_prompts(SPEC2, SCRIPT, None) == []


def test_check_requires_style_locks_and_verbatim_dialogue():
    errs = pt.check_prompts({**SPEC2, "prompts": [dict(SPEC2["prompts"][0], locks=["realism"], dialogue="wrong words")]}, SCRIPT, None)
    assert any("missing locks: product, notext, voice, look, pacing" in e for e in errs) and any("dialogue" in e for e in errs)


def test_flow_limits_attach_and_length():
    bad = dict(SPEC2["prompts"][0], attach=[f"@Image{i}" for i in range(1, 9)], gen_len_s=9)
    errs = pt.check_prompts({**SPEC2, "prompts": [bad]}, SCRIPT, None)
    assert any("7 attachments" in e for e in errs) and any("4–8 s" in e for e in errs)


def test_short_span_needs_use_when_generated_longer():
    short = dict(SPEC2["prompts"][0], vo_in_f=0, vo_out_f=72, gen_len_s=4)        # 2.4 s span
    assert any("use" in e for e in pt.check_prompts({**SPEC2, "prompts": [short]}, SCRIPT, None))
    assert pt.check_prompts({**SPEC2, "prompts": [dict(short, use="0:00-2:12")]}, SCRIPT, None) == []


def test_span_must_match_timings_within_two_frames():
    timings = {"lines": [{"start": 0.0, "end": 2.5}, {"start": 2.5, "end": 6.0}]}
    off = dict(SPEC2["prompts"][0], line=1, vo_in_f=0, vo_out_f=90)                 # line 1 ends at frame 75
    assert any("±2 frames" in e for e in pt.check_prompts({**SPEC2, "prompts": [off]}, SCRIPT, timings))


def test_keyframe_kind_renders_storyboard_table_and_skips_vo_rules():
    kf = dict(SPEC2["prompts"][0], id="SB-3", kind="keyframe", vo_in_f=0, vo_out_f=1, dialogue="")
    out = pt.render_prompts({**SPEC2, "prompts": [kf]}, SCRIPT, None)
    assert "# | Script line | Shot | Save as" in out and "SB-3.png" in out
    assert pt.check_prompts({**SPEC2, "prompts": [kf]}, SCRIPT, None) == []


def test_product_ad_needs_no_script():
    spec = {**SPEC2, "style": "product-ad", "prompts": [dict(SPEC2["prompts"][0], locks=["product", "notext"], dialogue="")]}
    assert pt.check_prompts(spec, [], None) == []


def test_seedance_prompt_starts_on_image1_and_needs_four_seconds():
    sd = {**SPEC2, "mode": "seedance", "prompts": [dict(SPEC2["prompts"][0], gen_len_s=3, vo_out_f=90)]}
    out = pt.render_prompts(sd, SCRIPT, None)
    assert out.split("```")[1].lstrip().startswith("Start on @Image1")
    assert any("at least 4 s" in e for e in pt.check_prompts(sd, SCRIPT, None))


def test_two_prompts_one_line_need_a_cut_point_and_unknown_attach_key():
    a = dict(SPEC2["prompts"][0], attach=["@Image9"])
    b = dict(SPEC2["prompts"][1], line=1, vo_in_f=60)
    errs = pt.check_prompts({**SPEC2, "prompts": [a, b]}, SCRIPT, None)
    assert any("cut point" in e for e in errs) and any("@Image9" in e for e in errs)


def test_cli_prompts_and_check_prompts(tmp_path):
    spec, script = tmp_path / "p2.json", tmp_path / "script.txt"
    spec.write_text(json.dumps(SPEC2), encoding="utf-8")
    script.write_text("\n".join(SCRIPT), encoding="utf-8")
    tool = str(Path(pt.__file__))
    r = subprocess.run([sys.executable, tool, "check-prompts", str(spec), "--script", str(script)], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["ok"] is True
    out = tmp_path / "prompts.txt"
    r = subprocess.run([sys.executable, tool, "prompts", str(spec), "--script", str(script), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0 and "AI-2" in out.read_text(encoding="utf-8")


CLIENT = {"id": "C-1", "kind": "client", "line": 3, "file": "D:/Footage/pour.mp4", "in_f": 12, "out_f": 66,
          "vo_in_f": 240, "vo_out_f": 294}


def test_client_rows_render_in_script_order_without_a_code_block():
    spec = {**SPEC2, "prompts": [CLIENT, *SPEC2["prompts"], dict(CLIENT, id="C-2", line=1, vo_in_f=60, vo_out_f=120,
                                                                    file="D:/Footage/jar.mp4", slot="TOP")]}
    out = pt.render_prompts(spec, SCRIPT, None)
    rows = [l for l in out.splitlines() if l.startswith("| ") and "(generate)" in l or l.startswith("| C-")]
    assert [r.split(" | ")[0] for r in rows] == ["| AI-1 (generate)", "| C-2", "| AI-2 (generate)", "| C-1"]
    c1 = next(r for r in rows if r.startswith("| C-1"))
    assert "D:/Footage/pour.mp4" in c1 and "0:12–2:06" in c1 and "8:00" in c1
    assert "TOP: D:/Footage/jar.mp4" in out and len(out.split("```")[1::2]) == 2 and "**C-1**" not in out


def test_client_rows_skip_lock_rules_but_check_their_span():
    spec = {**SPEC2, "prompts": [*SPEC2["prompts"], CLIENT]}
    assert pt.check_prompts(spec, SCRIPT, None) == []
    timings = {"lines": [{"start": 0.0, "end": 4.0}, {"start": 4.0, "end": 8.0}, {"start": 8.0, "end": 9.8}]}
    assert pt.check_prompts(spec, SCRIPT, timings) == []
    off = {**SPEC2, "prompts": [dict(CLIENT, vo_out_f=320)]}
    assert any("C-1" in e and "line 3" in e for e in pt.check_prompts(off, SCRIPT, timings))
    assert any("in_f" in e for e in pt.check_prompts({**SPEC2, "prompts": [dict(CLIENT, out_f=None)]}, SCRIPT, None))


def test_split_line_rows_together_cover_the_line():
    timings = {"lines": [{"start": 0.0, "end": 4.0}, {"start": 4.0, "end": 8.0}, {"start": 8.0, "end": 9.8}]}
    a = dict(CLIENT, vo_out_f=270, out_f=42)
    b = dict(CLIENT, id="C-2", vo_in_f=270, file="D:/Footage/b.mp4", in_f=0, out_f=24)
    assert pt.check_prompts({**SPEC2, "prompts": [a, b]}, SCRIPT, timings) == []
    gap = dict(b, vo_out_f=280)
    assert any("line 3" in e for e in pt.check_prompts({**SPEC2, "prompts": [a, gap]}, SCRIPT, timings))
    assert any("cut point" in e for e in pt.check_prompts({**SPEC2, "prompts": [a, dict(b, vo_in_f=250)]}, SCRIPT, None))


def test_product_ad_client_rows_need_no_script_and_follow_beats():
    pa = {**SPEC2, "style": "product-ad", "prompts": [
        {"id": "2", "kind": "client", "file": "D:/F/sole.mp4", "in_f": 0, "out_f": 60, "at_f": 90},
        {"id": "1", "kind": "client", "file": "D:/F/lift.mp4", "in_f": 30, "out_f": 120, "at_f": 0}]}
    assert pt.check_prompts(pa, [], None) == []
    rows = [l for l in pt.render_prompts(pa, [], None).splitlines() if l.startswith("| 1 ") or l.startswith("| 2 ")]
    assert [r.split(" | ")[0] for r in rows] == ["| 1", "| 2"] and "D:/F/lift.mp4" in rows[0]
    assert any("in_f" in e for e in pt.check_prompts({**pa, "prompts": [dict(pa["prompts"][0], out_f=0)]}, [], None))


def test_client_cut_length_must_match_the_vo_span():
    errs = pt.check_prompts({**SPEC2, "prompts": [dict(CLIENT, out_f=40)]}, SCRIPT, None)   # 28-frame cut, 54-frame span
    assert any("C-1" in e and "cut" in e for e in errs)
    assert pt.check_prompts({**SPEC2, "prompts": [dict(CLIENT, fps=25, in_f=0, out_f=45)]}, SCRIPT, None) == []  # 1.8 s


def test_ugc_host_block_says_the_words_once():
    host = dict(SPEC2["prompts"][0], action='0.0-4.0s: she lifts the bottle and says: "Meet Nativia, the vitamin I never skip."')
    block = pt.render_prompts({**SPEC2, "prompts": [host]}, SCRIPT, None).split("```")[1]
    assert block.count("the vitamin I never skip") == 1 and "Dialogue:" not in block
    split = dict(host, action='0.0-1.5s: she says: "Meet Nativia," 1.5-4.0s: she smiles: "the vitamin I never skip."')
    assert "Dialogue:" not in pt.render_prompts({**SPEC2, "prompts": [split]}, SCRIPT, None).split("```")[1]
    plain = pt.render_prompts(SPEC2, SCRIPT, None).split("```")[1]   # action without the quote: Dialogue printed
    assert plain.count("Meet Nativia, the vitamin I never skip.") == 1 and "Dialogue:" in plain
    assert pt.check_prompts({**SPEC2, "prompts": [host]}, SCRIPT, None) == []


def test_image_prompts_need_no_voice_or_pacing_lock():
    kf = dict(SPEC2["prompts"][0], id="SB-1", kind="keyframe", locks=["realism", "product", "notext", "look"], dialogue="")
    sheet = dict(SPEC2["prompts"][0], id="CS-1", kind="character", locks=["realism", "notext", "look"], dialogue="")
    assert pt.check_prompts({**SPEC2, "prompts": [kf, sheet]}, SCRIPT, None) == []
    bare = dict(kf, locks=["realism", "notext"])
    assert any("missing locks: product, look" in e for e in pt.check_prompts({**SPEC2, "prompts": [bare]}, SCRIPT, None))
    clay = {**SPEC2, "style": "claymation", "locks": {"style_bible": "CLAY", "notext": "NO TEXT"},
            "prompts": [dict(kf, locks=["style_bible", "notext"]), dict(sheet, locks=["style_bible", "notext"])]}
    assert pt.check_prompts(clay, SCRIPT, None) == []
    video = dict(SPEC2["prompts"][0], locks=["realism", "product", "notext", "look"])
    assert any("voice, pacing" in e for e in pt.check_prompts({**SPEC2, "prompts": [video]}, SCRIPT, None))


# --- Generator rules from generators.json (Task H: Higgsfield replaces Seedance) ---
GENERATORS = json.loads((Path(pt.__file__).resolve().parents[1] / "generators.json").read_text(encoding="utf-8"))
NINE = {f"@Image{i}": f"refs/{i}.png" for i in range(1, 10)}


def _hf(model, **prompt):
    return {**SPEC2, "mode": "prompts", "generator": "higgsfield", "generator_model": model,
            "prompts": [dict(SPEC2["prompts"][0], **prompt)]}


def test_generators_json_rows():
    gens = GENERATORS["generators"]
    flow = gens["google-flow"]
    assert (flow["min_s"], flow["max_s"], flow["max_attach"], flow["start_line"]) == (4, 8, 7, None)
    models = gens["higgsfield"]["models"]
    assert {"seedance-2.0", "seedance-2.5", "kling-3.0", "veo-3.1"} <= set(models)
    assert all(m["verified"] is None for m in models.values())       # nobody has confirmed the Higgsfield limits
    for mid in ("seedance-2.0", "seedance-2.5"):                      # today's Seedance rules, unchanged
        m = models[mid]
        assert (m["min_s"], m.get("max_s"), m["max_attach"], m["start_line"]) == (4, None, None, "Start on @Image1.")
    assert models["veo-3.1"]["lengths_s"] == [4, 6, 8]
    assert GENERATORS["aliases"]["seedance"] == {"generator": "higgsfield", "model": "seedance-2.0"}


def test_higgsfield_seedance_starts_on_image1_needs_4s_and_has_no_attachment_cap():
    spec = {**_hf("seedance-2.5", gen_len_s=3, vo_out_f=90, attach=list(NINE)), "attach": NINE}
    assert pt._block(spec, spec["prompts"][0]).startswith("Start on @Image1.\n")
    errs = pt.check_prompts(spec, SCRIPT, None)
    assert any("at least 4 s" in e for e in errs)
    assert not any("attachments" in e for e in errs)


def test_flow_has_no_start_line():
    assert not pt._block(SPEC2, SPEC2["prompts"][0]).startswith("Start")


def test_veo_fixed_lengths():
    errs = pt.check_prompts(_hf("veo-3.1", gen_len_s=5, vo_out_f=150), SCRIPT, None)
    assert any("4, 6 or 8 s" in e and "5 s" in e for e in errs)
    assert not any("4, 6 or 8" in e for e in pt.check_prompts(_hf("veo-3.1", gen_len_s=4), SCRIPT, None))


def test_unknown_model_uses_the_strictest_rules_with_a_warning_not_an_error():
    spec = {**_hf("hailuo-02", gen_len_s=9, vo_out_f=270, attach=["@Image1", "@Image2", "@Image3", "@Image4"]),
            "attach": NINE}
    errs = pt.check_prompts(spec, SCRIPT, None)
    assert any("5–8 s" in e and "got 9 s" in e for e in errs)   # the strictest range in the table (Kling 5, Flow/Veo 8)
    assert any("3 attachments" in e for e in errs)
    warns = pt.prompt_warnings(spec)
    assert len(warns) == 1 and "hailuo-02" in warns[0] and "generators.json" in warns[0]
    assert not any("generators.json" in e for e in errs)
    assert pt._block(spec, spec["prompts"][0]).startswith("Start from the attached image.\n")


def test_unverified_model_warns_and_check_still_passes(tmp_path):
    spec = _hf("kling-3.0", gen_len_s=5, vo_out_f=150)
    spec["prompts"][0]["action"] = "0.0-5.0s: she smiles and lifts the bottle"
    assert pt.check_prompts(spec, SCRIPT, None) == []
    assert pt.prompt_warnings(spec) == [
        "limits for Higgsfield · Kling 3.0 are not verified; check them in generators.json"]
    assert pt.prompt_warnings(SPEC2) == []          # Google Flow: today's numbers, verified
    f, script = tmp_path / "p2.json", tmp_path / "script.txt"
    f.write_text(json.dumps(spec), encoding="utf-8")
    script.write_text("\n".join(SCRIPT), encoding="utf-8")
    r = subprocess.run([sys.executable, str(Path(pt.__file__)), "check-prompts", str(f), "--script", str(script)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True and out["warnings"] == pt.prompt_warnings(spec)
    assert r.stderr.strip().splitlines() == [
        "warning: limits for Higgsfield · Kling 3.0 are not verified; check them in generators.json"]


OLD_SEEDANCE_BLOCK = (
    "Start on @Image1.\nSubject: young woman holding the bottle\nSetting: bathroom mirror\n"
    "Action: 0.0-4.0s: she smiles and lifts the bottle\nCamera: selfie, handheld\n"
    "Dialogue: Meet Nativia, the vitamin I never skip.\n"
    "REALISM LOCK: shot on a phone, natural light, no studio polish.\n"
    "PRODUCT LOCK: the Nativia bottle, white label, green cap, never altered.\n"
    "NO TEXT LOCK: no captions, subtitles or watermarks anywhere in frame.\n"
    "VOICE LOCK: same female voice, warm, mid pace, American accent.\n"
    "LOOK LOCK: bright bathroom, soft warm key, shallow depth of field.\n"
    "PACING LOCK: speak at a natural pace, no pauses over half a second.\n"
    "Attach: @Image1 = refs/R1_headshot.png, @Image2 = refs/product.png\nNegative: no extra people")
# sha256 of render_prompts for the old spec below, taken with the pre-Higgsfield plan_tools
OLD_SEEDANCE_RENDER_SHA = "5c38362477af2292eda93ce9de58bc46b946cab5b2fd7c16bdbc817725e6f79e"


def test_old_seedance_spec_renders_byte_identical():
    import hashlib
    kf = dict(SPEC2["prompts"][0], id="SB-1", kind="keyframe", locks=["realism", "product", "notext", "look"], dialogue="")
    old = {**SPEC2, "mode": "seedance", "generator": "seedance", "prompts": SPEC2["prompts"] + [kf]}
    assert pt._block(old, old["prompts"][0]) == OLD_SEEDANCE_BLOCK
    assert hashlib.sha256(pt.render_prompts(old, SCRIPT, None).encode()).hexdigest() == OLD_SEEDANCE_RENDER_SHA
    assert pt.check_prompts(old, SCRIPT, None) == []
    long = {**old, "attach": NINE, "prompts": [dict(SPEC2["prompts"][0], attach=list(NINE), gen_len_s=12, use="0:00-4:00")]}
    assert pt.check_prompts(long, SCRIPT, None) == []   # Seedance: no attachment cap, no maximum length (as before)
