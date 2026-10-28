"""Write a demo job for manual checks and screenshots of the companion GUI.

    run gui/demo.py <folder> [--root <root>]

Makes the "Uvola Cereza Ácida" job the reviewed mockup shows: a Spanish UGC ad with TEMP_EN on, brief and script
done, the storyboard waiting on the editor (8 beats and a character sheet in storyboard/storyboard.json, keyframes
SB-1, SB-2, SB-4, SB-7 and CHAR-1 as plain colour PNGs from ffmpeg), a QA table, Claude's activity and an open gate
with an "approve" question. Everything goes through jobstate / job.py, as Claude would write it.

<folder> must not have a job yet. With --root, <folder> must be a video folder of that root (a direct subfolder),
so the GUI server started on that root can open it. The folder becomes the "current" job ({tmp}/gui/current.json;
EDIT_MO_TO_GUI_TMP overrides {tmp}). Needs ffmpeg on PATH. Prints {"ok": true, "folder": ...}.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

GUI = Path(__file__).resolve().parent
if str(GUI) not in sys.path:
    sys.path.insert(0, str(GUI))

import folders  # noqa: E402
import job  # noqa: E402
import jobstate as js  # noqa: E402

CHARACTER = {"id": "CHAR-1", "name": "Sofía, 28, host", "status": "image",
             "prompt": "Character sheet, 4 views (front, 3/4, side, back) of Sofía, 28-year-old Latina woman, shoulder-length "
                       "wavy dark brown hair, warm olive skin, light freckles, casual cream knit top, natural makeup, neutral "
                       "mid-gray studio background, soft even light, 9:16, photoreal."}

BEATS = [
    ("SB-1", "¿Sabías que una cereza…", "Did you know one cherry…", "0:00–2:12",
     {"type": "ai", "framing": "Close-up", "camera": "push-in"}, "image",
     "Selfie close-up, Sofía holds a single glossy sour cherry next to her face, raised eyebrow, bright kitchen daylight "
     "from window left, shallow depth of field, 9:16, photoreal, no text.", "Curious, playful hook; the cherry is the hero"),
    ("SB-2", "…más vitamina C que una naranja", "…more vitamin C than an orange", "2:12–4:20",
     {"type": "ai", "framing": "Split screen", "camera": "static overhead"}, "image",
     "Overhead split: left a halved orange, right a small pile of sour cherries on a white marble counter, morning "
     "light, crisp product photography, 9:16, no text.", "Clean comparison, bright and crisp"),
    ("SB-3", "Llevo tres semanas…", "I've been taking this for three weeks…", "4:20–7:05",
     {"type": "client", "file": "host_take3.mp4", "t": 12.4}, "changed", None, "Use the take where she smiles at the end"),
    ("SB-4", "Uvola Cereza Ácida viene en gomitas…", "Uvola Sour Cherry comes in gummies…", "7:05–10:18",
     {"type": "ai", "framing": "Product hero", "camera": "slow orbit"}, "image",
     "Product hero, Uvola Cereza Ácida jar on a sunlit counter, label facing camera, gummies spilling from the open lid, "
     "slow orbit, 9:16, photoreal.", "Label readable, warm reds"),
    ("SB-5", "…sin azúcar añadida", "…no added sugar", "10:18–12:20",
     {"type": "ai", "framing": "Macro", "camera": "slow rotate"}, "prompt",
     "Macro, a single gummy rotating slowly on a white surface, sugar-free matte texture, red translucent glow, studio rim "
     "light, shallow depth of field, 9:16, photoreal, no text.", "Clean, clinical-but-warm macro; red glow ties to the cherry"),
    ("SB-6", "Dos al día, y listo.", "Two a day, and that's it.", "12:20–14:28",
     {"type": "ai", "framing": "Medium", "camera": "handheld"}, None,
     None, "Show her taking two, not one"),  # prompt null: written after the character sheet, as the GUI says
    ("SB-7", "Pruébalo hoy…", "Try it today…", "14:28–16:15",
     {"type": "ai", "framing": "Selfie", "camera": "point down"}, "image",
     "Selfie, Sofía points down toward the bottom of frame, jar held up beside her face, confident smile, kitchen "
     "background softly blurred, 9:16, photoreal.", "Confident close"),
    ("SB-8", "…link abajo.", "…link below.", "16:15–18:00",
     {"type": "graphic", "template": "cta-pill"}, "prompt",
     "End card: jar centered on a soft red gradient, space at the bottom for the CTA pill overlay, 9:16, no text.",
     "End card with the CTA pill (HyperFrames)"),
]
KEYFRAMES = {"SB-1": "0xA0343F", "SB-2": "0xC98A2E", "SB-4": "0xB2283B", "SB-7": "0x93324A", "CHAR-1": "0x8A4A5C"}

SCRIPT = [("H1", "¿Sabías que una cereza tiene más vitamina C que una naranja?",
           "Did you know one cherry has more vitamin C than an orange?"),
          ("H2", "Llevo tres semanas tomando esto y mi piel lo nota.", "I've been taking this for three weeks and my skin shows it."),
          ("B1", "Uvola Cereza Ácida viene en gomitas, sin azúcar añadida.", "Uvola Sour Cherry comes in gummies, no added sugar."),
          ("B2", "Dos al día, y listo.", "Two a day, and that's it."),
          ("CTA", "Pruébalo hoy, link abajo.", "Try it today, link below.")]

CHECKLIST = {"style": "UGC selfie review", "language": "es",
             "rules": [{"n": 1, "rule": "Length 25–35 s per video", "source": "brief p.1", "status": "confirmed"},
                       {"n": 2, "rule": "9:16, 1080×1920, 30 fps", "source": "brief p.1", "status": "confirmed"},
                       {"n": 3, "rule": "Show the product label in the first 3 s", "source": "brief p.2", "status": "confirmed"},
                       {"n": 4, "rule": "Never say “cura” or make medical claims", "source": "brief p.2", "status": "confirmed"},
                       {"n": 5, "rule": "Hooks under 3 s", "source": "editor, 2026-10-27", "status": "confirmed"}],
             "questions": [{"id": "cta", "text": "Should the CTA say “Compra ahora” or the brief's “Pruébalo hoy”?",
                            "why": "Changes the last 2 s of every timeline."}]}

QA = {"verdict": "1 FAIL", "passed": False,
      "rows": [{"n": 1, "check": "Script length 25–35 s", "status": "PASS", "evidence": "31:04 estimated", "fix": "",
                "timeline": "all"},
               {"n": 2, "check": "Label in the first 3 s", "status": "PASS", "evidence": "SB-1 at 1:10", "fix": "",
                "timeline": "Hook 1"},
               {"n": 3, "check": "No medical claims", "status": "PASS", "evidence": "no “cura”", "fix": "", "timeline": "all"},
               {"n": 4, "check": "Hooks under 3 s", "status": "FAIL", "evidence": "H2 reads 3:08",
                "fix": "trim “y mi piel lo nota” or speed up", "timeline": "Hook 2"},
               {"n": 5, "check": "TEMP_EN review track", "status": "OPEN", "evidence": "Spanish script, English lines on",
                "fix": "delete before export", "timeline": "all"}]}

GATE = {"title": "approve the storyboard direction",
        "detail": "4 of 8 shots have keyframes. You can approve now or after adding the rest.",
        "questions": [{"id": "approve", "kind": "confirm", "text": "Approve the storyboard direction?",
                       "why": "Claude writes the clip prompts from these shots next."}]}


def _job(*argv) -> dict:
    """Run one job.py command in-process (same parser and checks Claude uses)."""
    a = job.build_parser().parse_args([str(x) for x in argv])
    a.folder = Path(a.folder).resolve()
    return a.fn(a)


def _png(path: Path, colour: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=540x960",
                    "-frames:v", "1", str(path)], check=True)


def make(folder: Path) -> Path:
    folder = Path(folder)
    _job("init", folder, "--client", "Uvola", "--product", "Cereza Ácida gummies")
    _job("card", folder, "style=UGC selfie review", "language=Spanish (es)", "temp_en=on", "generator=Higgsfield · Seedance 2.5",
         "timelines=Hook 1|Hook 2|Hook 3")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        def file(name, data):
            p = td / name
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return p

        _job("output", folder, "brief", "checklist", "--file", file("checklist.json", CHECKLIST))
        _job("output", folder, "script", "script", "--file", file("script.json", {
            "lang": "es", "temp_en": True, "lines": [{"id": i, "text": t, "en": en} for i, t, en in SCRIPT]}))
        _job("output", folder, "script", "qa", "--from", "qa", file("qa.json", QA))
        _job("step", folder, "brief", "done", "--note", "Checklist confirmed")
        _job("step", folder, "script", "done", "--note", "Approved")
        _job("log", folder, "[brief] Read the brief: 5 rules, style UGC selfie review, Spanish script (TEMP_EN on)")
        _job("log", folder, "[script] Wrote 5 lines; QA: 3 PASS, 1 FAIL, 1 OPEN")
        _job("log", folder, "[storyboard] Wrote 8 storyboard shots and 1 character sheet")

        sb = folder / "storyboard"
        sb.mkdir(parents=True, exist_ok=True)
        beats = [{"id": i, "line": line, "en": en, "est": est, "shot": shot, "prompt": prompt, "status": status, "visual": visual}
                 for i, line, en, est, shot, status, prompt, visual in BEATS]
        board = {"title": "Uvola Cereza Ácida · Hook 1", "direction": "Bright kitchen daylight, handheld selfie, warm reds",
                 "characters": [CHARACTER], "beats": beats}
        (sb / "storyboard.json").write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
        for name, colour in KEYFRAMES.items():
            _png(sb / f"{name}.png", colour)

        seen = js.append_event(folder, {"type": "message", "step": "storyboard",
                                        "text": "use the take where she smiles at the end"})
        _job("handled", folder, seen["seq"])
        _job("log", folder, "[storyboard] Updated SB-3 to host_take3.mp4 @ 12.4 s, as you asked")
        _job("gate", folder, "storyboard", "--file", file("gate.json", GATE))
        _job("log", folder, "[storyboard] Waiting: storyboard approval")
    return folder


def main(argv: "list[str] | None" = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("folder")
    p.add_argument("--root", help="the GUI root; the folder must be one of its video folders")
    a = p.parse_args(argv)
    folder = Path(a.folder).resolve()
    try:
        if a.root and not folders.is_video_folder(folder, a.root):
            raise ValueError(f"{folder} is not a video folder of {a.root} (it must be a direct subfolder)")
        if (js.state_dir(folder) / "job.json").exists():
            raise ValueError(f"{folder} already has a job; pick a new folder for the demo")
        make(folder)
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"ok": True, "folder": folder.as_posix()}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
