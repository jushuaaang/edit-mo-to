"""ffmpeg preview of a plan (approximates the CapCut composite): punch-in cuts + overlays + sound cues -> mp4.

usage: python plan_preview.py plan.json out.mp4 [t1,t2,...]   (optional times -> one frame each, out.f<i>.png)
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_build as pb  # noqa: E402


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        raise SystemExit(__doc__)
    plan = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    out = Path(argv[1])
    F = lambda n: n / 30
    inputs, chains = [], []
    for i, (file, src_in, a, b, scale) in enumerate(plan["segs"]):
        inputs += ["-ss", f"{src_in:.4f}", "-t", f"{F(b) - F(a):.4f}", "-i", plan["clips_dir"] + file]
        w, h = round(1080 * scale / 2) * 2, round(1920 * scale / 2) * 2
        # CapCut fits the source inside the canvas, then applies the seg's scale
        pw, ph = max(w, 1080), max(h, 1920)
        chains.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                      f"pad={pw}:{ph}:(ow-iw)/2:(oh-ih)/2,crop=1080:1920,setsar=1,fps=30,trim=duration={F(b) - F(a):.4f},"
                      f"setpts=PTS-STARTPTS[v{i}];[{i}:a]atrim=duration={F(b) - F(a):.4f},asetpts=PTS-STARTPTS[a{i}]")
    n = len(plan["segs"])
    graph = ";".join(chains) + ";" + "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[base][aud]"
    last, k = "base", n
    for j, o in enumerate(plan["overlays"]):
        f = o.get("file") or str(Path(plan["motion_dir"]) / f"{j + 1:02d}_{o['template']}.mov")
        inputs += ["-itsoffset", f"{F(o['from']):.4f}", "-i", f]
        graph += f";[{last}][{k}:v]overlay=eof_action=pass:enable='between(t,{F(o['from']):.4f},{F(o['to']):.4f})'[o{j}]"
        last, k = f"o{j}", k + 1
    for j, o in enumerate(plan["overlays"]):  # speaker cutouts go above every overlay
        if not o.get("cutout"):
            continue
        f = o.get("cutout_file") or str(Path(plan["motion_dir"]) / f"{j + 1:02d}_cutout.mov")
        _, _, sc = pb.cutout_source(plan, o)
        inputs += ["-itsoffset", f"{F(o['from']):.4f}", "-i", f]
        w, h = round(1080 * sc / 2) * 2, round(1920 * sc / 2) * 2
        graph += (f";[{k}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,format=rgba,"
                  f"pad={max(w, 1080)}:{max(h, 1920)}:(ow-iw)/2:(oh-ih)/2:color=black@0,crop=1080:1920[c{j}]"
                  f";[{last}][c{j}]overlay=eof_action=pass:enable='between(t,{F(o['from']):.4f},{F(o['to']):.4f})'[oc{j}]")
        last, k = f"oc{j}", k + 1
    end_us = max(pb.US(b) for _, _, _, b, _ in plan["segs"])
    mix = ["[aud]"]
    if plan.get("music"):
        inputs += ["-i", plan["music"]["file"]]
        graph += f";[{k}:a]atrim=duration={end_us / 1e6:.3f},volume={plan['music'].get('volume', 0.1)}[mus]"
        mix.append("[mus]")
        k += 1
    for c, cue in enumerate(pb.sfx_cues(plan["overlays"], end_us)):
        inputs += ["-i", cue["file"]]
        ms = round(cue["at_us"] / 1000)
        graph += (f";[{k}:a]atrim=duration={cue['len_us'] / 1e6:.3f},afade=t=out:st={max(0, cue['len_us'] / 1e6 - 0.08):.3f}:d=0.08,"
                  f"volume={cue['volume']},adelay={ms}|{ms}[s{c}]")
        mix.append(f"[s{c}]")
        k += 1
    if len(mix) > 1:
        graph += f";{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first[mixed]"
        aout = "[mixed]"
    else:
        aout = "[aud]"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", f"[{last}]",
                    "-map", aout, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", str(out)], check=True)
    if len(argv) > 2:
        for i, t in enumerate(float(x) for x in argv[2].split(",")):
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(t), "-i", str(out), "-frames:v", "1",
                            "-vf", "scale=360:-1", str(out.with_suffix(f".f{i}.png"))], check=True)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1:])
