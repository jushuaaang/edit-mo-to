"""Voiceover line timings and music beats, in CapCut seconds:frames.

CLI (prints JSON):
    vo <audio> [script.txt] [--lang xx] [--fps 30]   word timestamps; with a script (one line per script line)
                                         returns each line's start/end/duration. Transcripts are
                                         cached in {tmp}/transcripts (--no-cache to redo)
    vo ... --compact                     same, as pipe text (lines n|start_sf|end_sf|matched|text, words
                                         word|start_f|end_f in frames): far fewer tokens for agents
    beats <audio> [--fps 30]             tempo and beat times, for cutting product ads to music
"""
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from machine import PATHS

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
    text = unicodedata.normalize("NFC", text).lower().replace("%", " percent")  # NFC keeps combining accents inside words
    toks = re.findall(r"(?:[^\W_]|')+", text)
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


def _cache_path(audio: Path, lang: str = "en") -> Path:
    """One transcript per file version, keyed on path + size + mtime, under {tmp}/transcripts."""
    import hashlib

    from machine import TMP

    st = Path(audio).stat()
    raw = f"{Path(audio).resolve()}|{st.st_size}|{st.st_mtime_ns}" + (f"_{lang}" if lang != "en" else "")  # English keys unchanged
    key = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return TMP / "transcripts" / f"{Path(audio).stem[:40]}_{key}.json"


def _cuda_count() -> int:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def _transcribe_faster_whisper(audio: Path, lang: str = "en") -> list[dict]:
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    def run(device: str, compute: str) -> list[dict]:
        # English keeps the english-only model; other languages need the multilingual one, told which language
        model = WhisperModel("small.en" if lang == "en" else "small", device=device, compute_type=compute)
        extra = {} if lang == "en" else {"language": lang}
        if device == "cpu":
            # the batched pipeline always applies VAD, which moves word starts (the cut points) by up to 5 frames,
            # for ~8% speed on a CPU: keep the plain call there
            segments, _ = model.transcribe(_load_16k(audio), word_timestamps=True, vad_filter=False, **extra)
        else:
            segments, _ = BatchedInferencePipeline(model).transcribe(_load_16k(audio), batch_size=8, word_timestamps=True, **extra)
        return [{"word": w.word.strip(), "start": w.start, "end": w.end} for s in segments for w in s.words]

    device = PATHS.get("asr_device", "auto")  # "cpu" skips the CUDA attempt (and its failed model load) entirely
    if device != "cpu" and _cuda_count() > 0:
        import ctranslate2

        # older GPUs (GTX 9xx) have no efficient float16; float32 on the GPU still beats the CPU
        compute = "float16" if "float16" in ctranslate2.get_supported_compute_types("cuda") else "float32"
        try:
            return run("cuda", compute)
        except (RuntimeError, ValueError):  # CUDA libraries (cublas) missing or unusable: use the CPU
            if device == "cuda":
                raise
    return run("cpu", "int8")


def _transcribe_mlx(audio: Path, lang: str = "en") -> list[dict]:
    import mlx_whisper

    extra = {} if lang == "en" else {"language": lang}  # English keeps auto-detect, as before
    res = mlx_whisper.transcribe(str(audio), path_or_hf_repo="mlx-community/whisper-large-v3-turbo", word_timestamps=True, **extra)
    return [{"word": w["word"].strip(), "start": w["start"], "end": w["end"]}
            for s in res["segments"] for w in s.get("words", [])]


def transcribe(audio: Path, cache: bool = True, backend: str | None = None, lang: str = "en") -> list[dict]:
    """Word timings. Cached, so a clip is transcribed once per job (vo, speech_cuts, re-runs)."""
    cached = _cache_path(audio, lang) if cache else None
    if cached and cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    backend = backend or PATHS.get("asr", "faster-whisper")
    words = _transcribe_mlx(audio, lang) if backend == "mlx" else _transcribe_faster_whisper(audio, lang)
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    return words


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


def compact(report: dict, fps: int = 30) -> str:
    """Pipe text of a vo report: lines n|start_sf|end_sf|matched|text, words word|start_f|end_f."""
    out = []
    if "lines" in report:
        out.append("# lines")
        out += [f"{i}|{l['start_sf']}|{l['end_sf']}|{int(l['matched'])}|{l['line']}" for i, l in enumerate(report["lines"], 1)]
    out.append("# words")
    out += [f"{w['word']}|{round(w['start'] * fps)}|{round(w['end'] * fps)}" for w in report.get("words", [])]
    return "\n".join(out)


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
    fps = 30
    if "--fps" in argv:
        i = argv.index("--fps")
        fps = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    lang = "en"
    if "--lang" in argv:
        i = argv.index("--lang")
        lang = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    cache = "--no-cache" not in argv
    as_compact = "--compact" in argv
    argv = [a for a in argv if a not in ("--no-cache", "--compact")]
    cmd, args = argv[0], argv[1:]
    if cmd == "vo":
        words = transcribe(Path(args[0]), cache, lang=lang)
        lines = None
        if len(args) > 1:
            lines = [l.strip() for l in Path(args[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
        out = vo_report(words, lines, fps)
    elif cmd == "beats":
        out = beats(Path(args[0]), fps)
    else:
        raise SystemExit(__doc__)
    print(compact(out, fps) if as_compact and cmd == "vo" else json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
