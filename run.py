"""Command-line versie (gebruikt door GitHub Actions).

Voorbeeld:
  python run.py --url https://www.youtube.com/watch?v=... --briefing briefings/borgh.md --out output
  python run.py --url ... --fragmenten "12:05-12:48, 1:02:10-1:02:55"   # zelf gekozen fragmenten
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pipeline as P


def parse_t(s):
    parts = [float(x) for x in s.strip().replace(",", ".").split(":")]
    t = 0.0
    for x in parts:
        t = t * 60 + x
    return t


def parse_fragments(text):
    text = text.strip()
    if text.startswith("["):  # vanuit de app: JSON met start/end/titel/hook/caption/beeld
        out = []
        for k, c in enumerate(json.loads(text), 1):
            out.append({"start": float(c["start"]), "end": float(c["end"]),
                        "title": c.get("title") or f"Fragment {k}", "hook": c.get("hook", ""),
                        "caption": c.get("caption", ""), "topic": c.get("topic", "handmatig"),
                        "reason": c.get("reason", "Bijgesteld in de app"),
                        **({"mode": c["mode"]} if c.get("mode") in ("crop", "blur") else {}),
                        **({"offset": float(c["offset"])} if c.get("offset") is not None else {})})
        return out
    out = []
    for k, chunk in enumerate([c for c in re.split(r"[;\n]|,\s(?=\d)", text) if c.strip()], 1):
        m = re.match(r"\s*([\d:.]+)\s*[-–]\s*([\d:.]+)\s*(.*)", chunk)
        if not m:
            raise SystemExit(f"Kan fragment niet lezen: '{chunk}'. Gebruik bv. 12:05-12:48")
        title = m.group(3).strip(" :|") or f"Fragment {k}"
        out.append({"start": parse_t(m.group(1)), "end": parse_t(m.group(2)), "title": title,
                    "hook": title if m.group(3).strip() else "", "caption": "", "topic": "handmatig",
                    "reason": "Zelf gekozen"})
    return out


def log(frac, msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg} {frac*100:.0f}%", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--briefing", default="")
    ap.add_argument("--extra", default="", help="extra instructies (worden aan briefing toegevoegd)")
    ap.add_argument("--glossary", default="")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--min-len", type=int, default=20)
    ap.add_argument("--max-len", type=int, default=60)
    ap.add_argument("--model", default="small")
    ap.add_argument("--mode", default="crop", choices=["crop", "blur"])
    ap.add_argument("--accent", default="#FF690A")
    ap.add_argument("--font", default="Borgh Sub")
    ap.add_argument("--fragmenten", default="")
    ap.add_argument("--voicenote-text", default="", help="uitgeschreven voicenote (tekstbestand)")
    ap.add_argument("--prepare-only", action="store_true", help="alleen downloaden + uitschrijven")
    ap.add_argument("--work", default="work")
    ap.add_argument("--out", default="output")
    a = ap.parse_args()

    work, out = Path(a.work), Path(a.out)
    work.mkdir(parents=True, exist_ok=True); (out / "reels").mkdir(parents=True, exist_ok=True)

    briefing = Path(a.briefing).read_text(encoding="utf-8") if a.briefing and Path(a.briefing).is_file() else ""
    vn = Path(a.voicenote_text) if a.voicenote_text else None
    if vn and vn.is_file() and vn.read_text(encoding="utf-8").strip():
        zinnen = [z.strip() for z in re.split(r"(?<=[.!?])\s+", vn.read_text(encoding="utf-8")) if len(z.strip()) > 3]
        briefing += "\n\nVoicenote van de klant (uitgeschreven, belangrijkste punten):\n" + \
                    "\n".join(f"- {z}" for z in zinnen)
    if a.extra.strip():
        briefing += "\n\nExtra instructies:\n" + a.extra.strip()

    src = next(iter(sorted(work.glob("source.mp4"))), None)
    meta = {}
    if src is None:
        src, meta = P.download(a.url, work, log)
        (work / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    elif (work / "meta.json").exists():
        meta = json.loads((work / "meta.json").read_text())
    print("Video:", meta.get("title"), "|", f"{P.probe_duration(src)/60:.1f} min", "|",
          "x".join(map(str, P.probe_size(src))), flush=True)

    tfile = work / "transcript.json"
    if tfile.exists():
        transcript = json.loads(tfile.read_text())
        print("Transcript uit cache", flush=True)
    else:
        transcript = P.transcribe(src, work, log, model_size=a.model, glossary=a.glossary)
    if a.prepare_only:
        print("Download en transcript klaar", flush=True)
        return

    if a.fragmenten.strip():
        raws = sorted(parse_fragments(a.fragmenten), key=lambda r: r["start"])  # snap sorteert ook
        clips = P.snap([dict(r) for r in raws], transcript, 1, 10_000)
        for c, raw in zip(clips, raws):  # handmatige tijden, beeld en hook exact respecteren
            c.update(start=raw["start"], end=raw["end"], hook=raw["hook"], caption=raw["caption"])
            c["mode"] = raw.get("mode", a.mode)
            if "offset" in raw:
                c["offset"] = raw["offset"]
        engine = "handmatig"
    else:
        clips, engine = P.find_highlights(transcript, briefing, a.n, a.min_len, a.max_len, log)
        for c in clips:
            c["mode"] = a.mode

    style = {"accent": a.accent, "font": a.font, "hook": True}
    logo = Path("assets/logo.png")
    rows = []
    for k, c in enumerate(clips, 1):
        log((k - 1) / len(clips), f"Reel {k}/{len(clips)} monteren: {c.get('title')}")
        mp4, txt = P.render_clip(src, c, transcript, out / "reels", style, logo)
        c["file"], c["txt"] = mp4, txt
        text = " ".join(s["text"] for s in transcript["segments"] if s["end"] > c["start"] and s["start"] < c["end"])
        rows.append((c, mp4, text))

    (out / "fragmenten.json").write_text(json.dumps(clips, ensure_ascii=False, indent=1))
    (out / "info.json").write_text(json.dumps({"engine": engine, "title": meta.get("title") or "",
                                               "duration": transcript.get("duration"), "briefing": briefing},
                                              ensure_ascii=False))
    (out / "transcript.json").write_text(json.dumps(
        [{"s": s["start"], "e": s["end"], "t": s["text"]} for s in transcript["segments"]], ensure_ascii=False))
    full = "\n".join(f"[{P.fmt_ts(s['start'])}] {s['text']}" for s in transcript["segments"])
    (out / "transcript.txt").write_text(full, encoding="utf-8")

    vid = re.search(r"(?:v=|youtu\.be/|live/)([\w-]{11})", a.url)
    yt = f"https://youtu.be/{vid.group(1)}" if vid else a.url
    md = [f"# Reels uit: {meta.get('title') or a.url}", "",
          f"Selectie: **{ {'claude': 'Claude', 'offline': 'trefwoorden uit de briefing (geen Claude-sleutel)', 'handmatig': 'zelf gekozen fragmenten'}[engine] }** · {len(rows)} reels", "",
          "| # | Reel | Tijd in stream | Lengte | Hook |", "|---|---|---|---|---|"]
    for c, mp4, _ in rows:
        md.append(f"| {c['id']} | {c.get('title','')} | [{P.fmt_ts(c['start'])} – {P.fmt_ts(c['end'])}]({yt}?t={int(c['start'])}) "
                  f"| {c['end']-c['start']:.0f}s | {c.get('hook','')} |")
    md += ["", "## Per reel", ""]
    for c, mp4, text in rows:
        md += [f"### {c['id']}. {c.get('title','')}", f"`{mp4}` · {P.fmt_ts(c['start'])} – {P.fmt_ts(c['end'])}", ""]
        if c.get("caption"):
            md += [f"**Caption:** {c['caption']}", ""]
        md += [f"> {text[:600]}", ""]
    md += ["", "**Fragment aanpassen?** Start de workflow opnieuw met dezelfde link en vul bij *fragmenten* "
           "de tijden in, bv. `12:05-12:48 Combi-Fix diepte; 1:02:10-1:02:55 Boren`. "
           "Download en transcriptie komen dan uit de cache, dus dat gaat snel."]
    (out / "OVERZICHT.md").write_text("\n".join(md), encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")
    print("\n".join(md), flush=True)
    print("===TRANSCRIPT===\n" + full + "\n===EINDE TRANSCRIPT===", flush=True)
    print("Klaar:", len(rows), "reels", flush=True)


if __name__ == "__main__":
    sys.exit(main())
