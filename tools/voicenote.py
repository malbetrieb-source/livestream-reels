"""Schrijft een voicenote (m4a/ogg/opus/webm/mp3/wav) uit naar platte tekst voor de briefing.

  python tools/voicenote.py voicenote.m4a voicenote.txt [modelgrootte] [woordenlijst]
"""
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    size = sys.argv[3] if len(sys.argv) > 3 else "small"
    glossary = sys.argv[4] if len(sys.argv) > 4 else ""
    wav = dst.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                   check=True)
    with wave.open(str(wav)) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    model = WhisperModel(size, device="auto", compute_type="int8")
    segs, _ = model.transcribe(audio, language="nl", vad_filter=True,
                               initial_prompt=(f"Woorden die voorkomen: {glossary}." if glossary else None))
    text = " ".join(s.text.strip() for s in segs).strip()
    dst.write_text(text, encoding="utf-8")
    wav.unlink(missing_ok=True)
    print("Voicenote uitgeschreven:\n" + text, flush=True)


if __name__ == "__main__":
    main()
