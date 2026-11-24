"""Livestream -> Reels pipeline.

Stappen: download (yt-dlp) -> transcriptie (faster-whisper) -> highlights (Claude of offline)
-> render naar 9:16 met ondertitels (ffmpeg).
"""
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


# ---------------------------------------------------------------- helpers

def fmt_ts(t):
    t = max(0.0, float(t))
    m, s = divmod(t, 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:04.1f}" if h else f"{m}:{s:04.1f}"


def slug(text, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n].strip("-") or "clip"


def probe_duration(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def probe_size(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    w, h = out.stdout.strip().split("\n")[0].split(",")[:2]
    return int(w), int(h)


def ffmpeg(args, log=None):
    p = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y"] + args,
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg fout: " + p.stderr[-1500:])


# ---------------------------------------------------------------- 1. download

def download(url, job_dir, progress):
    import yt_dlp

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                progress(d.get("downloaded_bytes", 0) / total, "Video downloaden")

    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(Path(job_dir) / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    if os.environ.get("YTDLP_COOKIES") and Path(os.environ["YTDLP_COOKIES"]).exists():
        opts["cookiefile"] = os.environ["YTDLP_COOKIES"]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    src = next(Path(job_dir).glob("source.*"))
    if src.suffix != ".mp4":  # zorg voor een browser-afspeelbare preview
        mp4 = Path(job_dir) / "source.mp4"
        ffmpeg(["-i", str(src), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-c:a", "aac", str(mp4)])
        src.unlink()
        src = mp4
    return src, {"title": info.get("title"), "channel": info.get("channel"),
                 "upload_date": info.get("upload_date")}


# ---------------------------------------------------------------- 2. transcriptie

def extract_audio(video, wav):
    ffmpeg(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])


def transcribe_faster_whisper(wav, progress, model_size="small", glossary=""):
    from faster_whisper import WhisperModel

    progress(0.0, f"Spraakmodel '{model_size}' laden (eerste keer wordt het gedownload)")
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    import wave
    import numpy as np
    with wave.open(str(wav)) as w:  # zelf inlezen: omzeilt PyAV-versieproblemen
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segments, info = model.transcribe(
        audio, language="nl", word_timestamps=True, vad_filter=True,
        initial_prompt=(f"Woorden die voorkomen: {glossary}." if glossary else None),
    )
    out = []
    for seg in segments:
        words = [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)}
                 for w in (seg.words or []) if w.word.strip()]
        out.append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                    "text": seg.text.strip(), "words": words})
        progress(min(seg.end / max(info.duration, 1), 0.999), "Transcriberen")
    return out


def transcribe(video, job_dir, progress, model_size="small", glossary="", backend=None):
    wav = Path(job_dir) / "audio.wav"
    progress(0.0, "Audio uitpakken")
    extract_audio(video, wav)
    fn = backend or transcribe_faster_whisper
    segs = fn(wav, progress, model_size=model_size, glossary=glossary)
    data = {"duration": probe_duration(video), "segments": segs}
    (Path(job_dir) / "transcript.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    wav.unlink(missing_ok=True)
    return data


# ---------------------------------------------------------------- 3. highlights

CLAUDE_PROMPT = """Je bent een ervaren social-video-editor voor een B2B-bevestigingsmiddelen- en gereedschapsmerk.
Hieronder staat het transcript van een YouTube-livestream (Nederlands, met tijdcodes in seconden) en een briefing van de klant.

Kies de {n} beste fragmenten om er losse verticale reels/shorts/TikToks van te maken.
Regels:
- Elk fragment is tussen {min_len} en {max_len} seconden lang.
- Een fragment moet op zichzelf te begrijpen zijn: begin bij het begin van een zin/uitleg, stop na de pointe. Geen half afgebroken zinnen.
- Volg de briefing: elk onderwerp dat de klant noemt krijgt bij voorkeur minstens één fragment, in de volgorde van belangrijkheid in de briefing.
- Voorkeur voor concrete tips, getallen, demonstraties, 'fout vs goed', en momenten met energie of humor.
- Fragmenten mogen elkaar niet overlappen.

Geef ALLEEN een JSON-array terug, zonder uitleg eromheen, met per fragment:
{{"start": <sec>, "end": <sec>, "topic": "<onderwerp uit briefing of eigen label>",
  "title": "<korte werktitel>", "hook": "<pakkende openingstekst voor in beeld, max 6 woorden>",
  "caption": "<social caption van 1-3 zinnen in de toon van een vakman, met 3-5 hashtags>",
  "reason": "<waarom dit werkt, 1 zin>"}}

BRIEFING:
{briefing}

TRANSCRIPT:
{transcript}
"""


def transcript_lines(segments):
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)


def highlights_claude(transcript, briefing, n, min_len, max_len):
    import anthropic

    client = anthropic.Anthropic()
    prompt = CLAUDE_PROMPT.format(n=n, min_len=min_len, max_len=max_len,
                                  briefing=briefing or "(geen briefing — kies zelf de sterkste momenten)",
                                  transcript=transcript_lines(transcript["segments"]))
    msg = client.messages.create(model=os.environ.get("REELS_MODEL", "claude-sonnet-5-5"),
                                 max_tokens=6000, messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    raw = json.loads(text[text.index("["): text.rindex("]") + 1])
    return [dict(c, source="claude") for c in raw]


STOP = set("""de het een en van in op te dat die is je we ik ze er niet met voor als aan bij ook nog maar
dan wel dus naar zijn wordt worden heb hebt hebben had was waren moet moeten kan kunnen gaat gaan
doen doet dit deze daar hier wat wie hoe waar wanneer omdat zoals eigenlijk gewoon natuurlijk even
echt beetje altijd nooit heel veel meer mensen ding dingen stuk iets alles allemaal zelf eruit
belangrijk belangrijke tweede derde laatste eerste sowieso overigens volgens misschien eventueel
zitten zit staan staat komt komen zeggen zeg zien kijken uitleggen uitlegt""".split())


def keywords(text):
    toks = re.findall(r"[a-zà-ÿ0-9\-]+", text.lower())
    return {t for t in toks if len(t) >= 4 and t not in STOP and not t.isdigit()} | \
           {t for t in toks if re.fullmatch(r"\d+(mm|cm)?", t) and len(t) >= 1}


def briefing_topics(briefing):
    topics = []
    for line in briefing.splitlines():
        m = re.match(r"\s*(?:[-–*•]|\d+[.)])\s+(.*)", line)
        if m and len(m.group(1)) > 3:
            topics.append(m.group(1).strip())
    return topics


def _windows(segs, min_len, max_len):
    for i in range(len(segs)):
        for j in range(i, len(segs)):
            dur = segs[j]["end"] - segs[i]["start"]
            if dur > max_len:
                break
            if dur >= min_len:
                yield i, j


def _match(tok, kws):
    return next((k for k in kws if tok.startswith(k[:max(4, len(k) - 2)])), None)


def _score(segs, i, j, kws, idf=None):
    """Score = som van gewichten van gevonden trefwoorden; zeldzame vaktermen tellen zwaarder."""
    idf = idf or {}
    toks = re.findall(r"[a-zà-ÿ0-9\-]+", " ".join(s["text"] for s in segs[i:j + 1]).lower())
    found = [k for k in (_match(t, kws) for t in toks) if k]
    uniq = set(found)
    dur = segs[j]["end"] - segs[i]["start"]
    return (sum(idf.get(k, 1.0) * 2 for k in uniq) + 0.3 * len(found)) / (1 + dur / 120)


def highlights_offline(transcript, briefing, n, min_len, max_len):
    """Zonder API-sleutel: per briefing-onderwerp het best passende fragment zoeken op trefwoorden."""
    segs = transcript["segments"]
    chosen = []
    seg_toks = [set(re.findall(r"[a-zà-ÿ0-9\-]+", s["text"].lower())) for s in segs]
    idf = {}
    for k in keywords(briefing or ""):
        df = sum(1 for st in seg_toks if any(_match(t, {k}) for t in st))
        idf[k] = math.log((len(segs) + 1) / (df + 0.5)) if df else 0.0

    def free(i, j):
        a, b = segs[i]["start"], segs[j]["end"]
        return all(b <= c["start"] or a >= c["end"] for c in chosen)

    def best_for(kws):
        best = None
        for i, j in _windows(segs, min_len, max_len):
            if not free(i, j):
                continue
            sc = _score(segs, i, j, kws, idf)
            if sc > 0 and (best is None or sc > best[0]):
                best = (sc, i, j)
        return best

    for topic in briefing_topics(briefing)[:n]:
        kws = keywords(topic)
        b = best_for(kws) if kws else None
        if b:
            _, i, j = b
            title = re.split(r"[:;.—(]", topic)[0].strip()[:50]
            chosen.append({"start": segs[i]["start"], "end": segs[j]["end"], "topic": title,
                           "title": title, "hook": title[:40], "caption": "", "reason": "Match op briefing-onderwerp",
                           "source": "offline"})
    all_kws = keywords(briefing) if briefing else set()
    while len(chosen) < n:
        b = best_for(all_kws) if all_kws else None
        if not b:  # geen briefing of geen hits meer: neem gelijk verdeelde fragmenten
            for i, j in _windows(segs, min_len, max_len):
                if free(i, j) and segs[i]["start"] >= (chosen[-1]["end"] if chosen else 0):
                    b = (0, i, j)
                    break
        if not b:
            break
        _, i, j = b
        words = [w for w in re.findall(r"[a-zà-ÿ\-]+", " ".join(s["text"] for s in segs[i:j + 1]).lower())
                 if w in all_kws][:3]
        title = " / ".join(dict.fromkeys(words)) or f"Fragment {fmt_ts(segs[i]['start'])}"
        chosen.append({"start": segs[i]["start"], "end": segs[j]["end"], "topic": title, "title": title,
                       "hook": title[:40], "caption": "", "reason": "Veel trefwoorden uit briefing",
                       "source": "offline"})
    return chosen


def snap(clips, transcript, min_len, max_len):
    """Rond start/eind af op zinsgrenzen en voeg 0,15 s lucht toe."""
    segs = transcript["segments"]
    dur = transcript.get("duration") or (segs[-1]["end"] if segs else 0)
    out = []
    for c in clips:
        s, e = float(c["start"]), float(c["end"])
        starts = [x["start"] for x in segs if x["start"] <= s + 1.0] or [s]
        ends = [x["end"] for x in segs if x["end"] >= e - 1.0] or [e]
        s2, e2 = max(starts), min(ends)
        if e2 - s2 < min_len * 0.6 or e2 - s2 > max_len * 1.3:
            s2, e2 = s, e
        c = dict(c, start=round(max(0, s2 - 0.15), 2), end=round(min(dur or e2 + 1, e2 + 0.3), 2))
        out.append(c)
    out.sort(key=lambda c: c["start"])
    for a, b in zip(out, out[1:]):  # padding mag geen overlap veroorzaken
        if b["start"] < a["end"]:
            mid = round((a["end"] + b["start"]) / 2, 2)
            a["end"], b["start"] = mid, mid
    for k, c in enumerate(out, 1):
        c.setdefault("caption", "")
        c.update(id=k, selected=True, mode=c.get("mode", "crop"), offset=c.get("offset", 0.5))
    return out


def find_highlights(transcript, briefing, n=8, min_len=20, max_len=60, progress=lambda *a: None):
    clips, engine = None, "offline"
    if os.environ.get("ANTHROPIC_API_KEY"):
        progress(0.2, "Claude zoekt de hoogtepunten")
        try:
            clips, engine = highlights_claude(transcript, briefing, n, min_len, max_len), "claude"
        except Exception as e:  # val terug op offline
            progress(0.5, f"Claude niet bereikbaar ({e.__class__.__name__}), offline selectie")
    if clips is None:
        progress(0.5, "Hoogtepunten zoeken op trefwoorden (offline)")
        clips = highlights_offline(transcript, briefing, n, min_len, max_len)
    return snap(clips, transcript, min_len, max_len), engine


# ---------------------------------------------------------------- 4. render

def _ass_color(hex_rgb, alpha="00"):
    h = hex_rgb.lstrip("#")
    return f"&H{alpha}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _ass_time(t):
    t = max(0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


def build_ass(words, clip_start, clip_end, hook, style):
    """Grote ondertitels, 3 woorden per regel, actieve woord in accentkleur."""
    font = style.get("font", "Arial Black")
    accent = _ass_color(style.get("accent", "#FFD400"))
    size = int(style.get("size", 82))
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Sub,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,80,80,520,1",
        f"Style: Hook,{font},{int(size*0.9)},&H00000000,&H00000000,{accent},{accent},-1,0,0,0,100,100,0,0,3,22,0,8,90,90,230,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if hook:
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(min(3.5, clip_end - clip_start))},Hook,,0,0,0,,"
                     f"{{\\fad(150,250)}}{_ass_escape(hook.upper())}")
    ws = [w for w in words if w["e"] > clip_start and w["s"] < clip_end]
    groups, cur = [], []
    for w in ws:
        if cur and (len(cur) >= 3 or w["s"] - cur[-1]["e"] > 0.6 or len(" ".join(x["w"] for x in cur + [w])) > 22):
            groups.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.?!,]$", w["w"]):
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    for gi, g in enumerate(groups):
        g_end = min(g[-1]["e"] + 0.25, groups[gi + 1][0]["s"] if gi + 1 < len(groups) else g[-1]["e"] + 0.6)
        for k, w in enumerate(g):
            a = w["s"] if k else min(w["s"], g[0]["s"])
            b = g[k + 1]["s"] if k + 1 < len(g) else g_end
            parts = [(f"{{\\c{accent}}}{_ass_escape(x['w'])}{{\\c&H00FFFFFF&}}" if x is w else _ass_escape(x["w"]))
                     for x in g]
            lines.append(f"Dialogue: 0,{_ass_time(a - clip_start)},{_ass_time(b - clip_start)},Sub,,0,0,0,,"
                         + " ".join(parts))
    return "\n".join(lines) + "\n"


def render_clip(src, clip, transcript, out_dir, style, logo=None):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    s, e = float(clip["start"]), float(clip["end"])
    name = f"{int(clip['id']):02d}_{slug(clip.get('title') or 'clip')}"
    words = [w for seg in transcript["segments"] for w in seg.get("words", [])]
    ass_path = out_dir / f"{name}.ass"
    ass_path.write_text(build_ass(words, s, e, clip.get("hook", "") if style.get("hook", True) else "", style),
                        encoding="utf-8")

    w, h = probe_size(src)
    if clip.get("mode") == "blur":
        vf = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
              "gblur=sigma=40,eq=brightness=-0.08[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]")
    else:
        off = min(max(float(clip.get("offset", 0.5)), 0), 1)
        vf = f"[0:v]scale=-2:1920,crop=1080:1920:(iw-1080)*{off:.3f}:0[v0]"
    sub_path = str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    vf += f";[v0]ass='{sub_path}'[v1]"
    inputs = ["-ss", f"{s:.2f}", "-t", f"{e - s:.2f}", "-i", str(src)]
    last = "[v1]"
    if logo and Path(logo).exists():
        inputs += ["-i", str(logo)]
        vf += ";[1:v]scale=220:-1[lg];[v1][lg]overlay=W-w-50:60[v2]"
        last = "[v2]"
    out = out_dir / f"{name}.mp4"
    ffmpeg(inputs + ["-filter_complex", vf, "-map", last, "-map", "0:a?",
                     "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                     "-r", "30", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    txt = out_dir / f"{name}.txt"
    txt.write_text(f"{clip.get('title','')}\n\n{clip.get('caption','')}\n\n"
                   f"Bron: {fmt_ts(s)} – {fmt_ts(e)} in de livestream\n", encoding="utf-8")
    ass_path.unlink(missing_ok=True)
    return out.name, txt.name
