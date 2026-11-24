"""Zet de uitkomst van een run klaar voor de app: previews (720p) + resultaat.json in map pub/.

  python tools/publish.py output pub --id <aanvraag> --url <youtube> --run-id <id> --run-url <url> --artifact <naam>
"""
import argparse
import json
import subprocess
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("pub")
    for k in ("id", "url", "run-id", "run-url", "artifact", "voicenote-text", "extra", "model", "mode"):
        ap.add_argument("--" + k, default="")
    a = ap.parse_args()
    out, pub = Path(a.out), Path(a.pub)
    (pub / "previews").mkdir(parents=True, exist_ok=True)

    clips = json.loads((out / "fragmenten.json").read_text())
    info = json.loads((out / "info.json").read_text()) if (out / "info.json").exists() else {}
    for c in clips:
        src = out / "reels" / c["file"]
        prev = f"previews/{int(c['id']):02d}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=720:1280",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-c:a", "aac", "-b:a", "96k",
                        "-movflags", "+faststart", str(pub / prev)], check=True)
        c["preview"] = prev

    vn = Path(a.voicenote_text) if a.voicenote_text else None
    res = {
        "id": a.id, "url": a.url, "title": info.get("title", ""), "engine": info.get("engine", ""),
        "duration": info.get("duration"), "run_id": a.run_id, "run_url": a.run_url, "artifact": a.artifact,
        "voicenote": vn.read_text(encoding="utf-8") if vn and vn.is_file() else "",
        "extra": a.extra, "briefing": info.get("briefing", ""), "model": a.model, "mode": a.mode, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "clips": clips,
    }
    (pub / "resultaat.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    if (out / "transcript.json").exists():
        (pub / "transcript.json").write_text((out / "transcript.json").read_text())
    print(f"{len(clips)} previews klaargezet", flush=True)


if __name__ == "__main__":
    main()
