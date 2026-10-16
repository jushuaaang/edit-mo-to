"""Voiceover line timings and music beats, in CapCut seconds:frames.

CLI (prints JSON):
    vo <audio> [script.txt] [--fps 30]   word timestamps; with a script (one line per script line)
                                         returns each line's start/end/duration
    beats <audio> [--fps 30]             tempo and beat times, for cutting product ads to music
"""
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

MATCH_THRESHOLD = 0.6
NUMBERS = {str(i): w for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}


def to_sf(seconds: float, fps: int = 30) -> str:
    """CapCut-style timecode: s:ff under a minute, m:ss:ff from 60s on."""
    frames = round(seconds * fps)
    secs, ff = divmod(frames, fps)
    if secs < 60:
        return f"{secs}:{ff:02d}"
    return f"{secs // 60}:{secs % 60:02d}:{ff:02d}"


def _tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9']+", text.lower().replace("%", " percent"))
    return [NUMBERS.get(t, t) for t in toks]


def align_lines(words: list[dict], lines: list[str], fps: int = 30) -> list[dict]:
    """Find each script line in the transcript, in order. Unmatched lines get the gap between neighbours."""
    flat = []  # one token per entry, carrying its word's times
    for w in words:
        for t in _tokens(w["word"]):
            flat.append({"tok": t, "start": w["start"], "end": w["end"]})
    toks = [f["tok"] for f in flat]

    spans = []
    cursor = 0
    for line in lines:
        lt = _tokens(line)
        best = (0.0, None, None)
        for a in range(cursor, len(toks)):
            for n in range(max(1, len(lt) - 2), len(lt) + 3):
                b = a + n
                if b > len(toks):
                    break
                score = SequenceMatcher(None, lt, toks[a:b]).ratio()
                if score > best[0]:
                    best = (score, a, b)
        if lt and best[0] >= MATCH_THRESHOLD:
            _, a, b = best
            spans.append((flat[a]["start"], flat[b - 1]["end"]))
            cursor = b
        else:
            spans.append(None)

    out = []
    for i, line in enumerate(lines):
        if spans[i]:
            start, end = spans[i]
        else:
            prev_end = next((s[1] for s in reversed(spans[:i]) if s), 0.0)
            next_start = next((s[0] for s in spans[i + 1:] if s), words[-1]["end"] if words else prev_end)
            start, end = prev_end, max(prev_end, next_start)
        out.append({"line": line, "start": round(start, 3), "end": round(end, 3),
                    "start_sf": to_sf(start, fps), "end_sf": to_sf(end, fps),
                    "duration": round(end - start, 3), "duration_sf": to_sf(end - start, fps),
                    "matched": spans[i] is not None})
    return out


def _load_16k(audio: Path):
    """Decode with ffmpeg; faster-whisper's own PyAV loader breaks on newer av releases."""
    import subprocess

    import numpy as np

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def transcribe(audio: Path) -> list[dict]:
    from faster_whisper import WhisperModel

    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(_load_16k(audio), word_timestamps=True, vad_filter=False)
    return [{"word": w.word.strip(), "start": w.start, "end": w.end} for s in segments for w in s.words]


def beats(audio: Path, fps: int = 30) -> dict:
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio), sr=None, mono=True)
    hop = 128  # ~6 ms at 22.05 kHz, so beats land on the right frame
    tempo, frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop)
    times = librosa.frames_to_time(frames, sr=sr, hop_length=hop)
    # beat_track snaps to a tempo grid that drifts (117.45 BPM for a 120 BPM click);
    # move each beat to the nearest real onset within 70 ms
    onsets = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop, units="time", backtrack=False)
    if len(onsets):
        nearest = onsets[np.abs(onsets[None, :] - times[:, None]).argmin(axis=1)]
        times = np.where(np.abs(nearest - times) <= 0.07, nearest, times)
    times = times.tolist()
    if len(times) > 1:
        tempo = 60.0 / float(np.median(np.diff(times)))
    return {"tempo": round(float(np.atleast_1d(tempo)[0]), 2),
            "beats": [round(t, 3) for t in times], "beats_sf": [to_sf(t, fps) for t in times]}


def vo_report(words: list[dict], lines: list[str] | None, fps: int = 30) -> dict:
    """Word timings always (agents cut mid-line on word gaps); line timings when a script is given."""
    out = {"words": [{**w, "start_sf": to_sf(w["start"], fps), "end_sf": to_sf(w["end"], fps)} for w in words],
           "total": to_sf(words[-1]["end"], fps) if words else "0:00"}
    if lines is not None:
        out["lines"] = align_lines(words, lines, fps)
    return out


def main(argv: list[str]) -> None:
    fps = 30
    if "--fps" in argv:
        i = argv.index("--fps")
        fps = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    cmd, args = argv[0], argv[1:]
    if cmd == "vo":
        words = transcribe(Path(args[0]))
        lines = None
        if len(args) > 1:
            lines = [l.strip() for l in Path(args[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
        out = vo_report(words, lines, fps)
    elif cmd == "beats":
        out = beats(Path(args[0]), fps)
    else:
        raise SystemExit(__doc__)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
