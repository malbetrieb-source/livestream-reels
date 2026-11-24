"""Lokale web-app: YouTube-livestream -> reels.  Start met ./start.command (Mac) of `python app.py`."""
import json
import os
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory, abort

import pipeline as P

ROOT = Path(__file__).parent
WORK = ROOT / "werkmap"
WORK.mkdir(exist_ok=True)
BRIEFINGS = ROOT / "briefings"
LOGO = ROOT / "assets" / "logo.png"
app = Flask(__name__)
LOCK = threading.Lock()
TRANSCRIBE_BACKEND = None  # alleen voor tests te overschrijven


def jpath(jid):
    p = WORK / jid
    if not p.is_dir() or "/" in jid or ".." in jid:
        abort(404)
    return p


def load(jid):
    return json.loads((jpath(jid) / "job.json").read_text())


def save(job):
    with LOCK:
        f = WORK / job["id"] / "job.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1))
        tmp.replace(f)


def updater(job, stage):
    def progress(frac, msg):
        job.update(stage=stage, progress=round(float(frac), 3), message=msg)
        save(job)
    return progress


def process(job, upload_path=None, voice_path=None):
    d = WORK / job["id"]
    try:
        if voice_path:
            pr = updater(job, "briefing")
            pr(0, "Voicenote met briefing uitschrijven")
            tmpdir = d / "voicenote"; tmpdir.mkdir(exist_ok=True)
            t = P.transcribe(voice_path, tmpdir, pr, model_size=job["model"], glossary=job["glossary"],
                             backend=TRANSCRIBE_BACKEND)
            spoken = " ".join(s["text"] for s in t["segments"])
            job["briefing"] = (job["briefing"] + "\n\nUit de voicenote:\n" + spoken).strip()
            save(job)
        if upload_path:
            src = Path(upload_path)
            job["meta"] = {"title": job.get("meta", {}).get("title") or src.name}
        else:
            src, meta = P.download(job["url"], d, updater(job, "download"))
            job["meta"] = meta
        job["source"] = src.name
        job["duration"] = P.probe_duration(src)
        save(job)
        tr = P.transcribe(src, d, updater(job, "transcribe"), model_size=job["model"],
                          glossary=job["glossary"], backend=TRANSCRIBE_BACKEND)
        clips, engine = P.find_highlights(tr, job["briefing"], job["n"], job["min_len"], job["max_len"],
                                          updater(job, "highlights"))
        job.update(clips=clips, engine=engine, status="review", stage="review", progress=1,
                   message=f"{len(clips)} fragmenten voorgesteld ({'Claude' if engine == 'claude' else 'offline trefwoorden'})")
        save(job)
    except Exception as e:
        job.update(status="error", message=str(e), trace=traceback.format_exc())
        save(job)


def render_all(job):
    d = WORK / job["id"]
    try:
        tr = json.loads((d / "transcript.json").read_text())
        sel = [c for c in job["clips"] if c.get("selected")]
        job["renders"] = []
        for k, c in enumerate(sel):
            job.update(status="rendering", stage="render", progress=k / max(len(sel), 1),
                       message=f"Reel {k+1} van {len(sel)} monteren: {c.get('title','')}")
            save(job)
            mp4, txt = P.render_clip(d / job["source"], c, tr, d / "reels", job["style"], LOGO)
            job["renders"].append({"id": c["id"], "title": c.get("title"), "mp4": mp4, "txt": txt})
            save(job)
        job.update(status="done", stage="done", progress=1, message=f"{len(sel)} reels klaar")
        save(job)
    except Exception as e:
        job.update(status="error", message=str(e), trace=traceback.format_exc())
        save(job)


# ---------------------------------------------------------------- routes

@app.get("/")
def index():
    jobs = []
    for f in sorted(WORK.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            j = json.loads(f.read_text())
            jobs.append(j)
        except Exception:
            pass
    briefs = {p.stem: p.read_text(encoding="utf-8") for p in sorted(BRIEFINGS.glob("*.md"))}
    page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    return page.replace("__JOBS__", json.dumps(jobs, ensure_ascii=False)) \
               .replace("__BRIEFINGS__", json.dumps(briefs, ensure_ascii=False)) \
               .replace("__CLAUDE__", "true" if os.environ.get("ANTHROPIC_API_KEY") else "false")


@app.post("/jobs")
def create_job():
    f = request.form
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = WORK / jid; d.mkdir()
    job = {"id": jid, "url": f.get("url", "").strip(), "briefing": f.get("briefing", "").strip(),
           "glossary": f.get("glossary", "").strip(), "model": f.get("model", "small"),
           "n": int(f.get("n", 8)), "min_len": int(f.get("min_len", 20)), "max_len": int(f.get("max_len", 60)),
           "style": {"accent": f.get("accent", "#FFD400"), "font": f.get("font", "Arial Black"), "hook": True},
           "status": "running", "stage": "start", "progress": 0, "message": "Gestart", "clips": [], "renders": [],
           "created": time.time()}
    upload = request.files.get("video")
    up_path = None
    if upload and upload.filename:
        ext = Path(upload.filename).suffix.lower() or ".mp4"
        up_path = d / f"source{ext}"
        upload.save(up_path)
        job["meta"] = {"title": upload.filename}
    elif not job["url"]:
        shutil.rmtree(d)
        return "Geef een YouTube-link of upload een videobestand.", 400
    voice = request.files.get("voicenote")
    v_path = None
    if voice and voice.filename:
        v_path = d / ("briefing" + (Path(voice.filename).suffix or ".opus"))
        voice.save(v_path)
    save(job)
    threading.Thread(target=process, args=(job, up_path, v_path), daemon=True).start()
    return redirect(f"/jobs/{jid}")


@app.get("/jobs/<jid>")
def job_page(jid):
    jpath(jid)
    return (ROOT / "templates" / "job.html").read_text(encoding="utf-8").replace("__JID__", jid)


@app.get("/api/jobs/<jid>")
def job_api(jid):
    return jsonify(load(jid))


@app.get("/api/jobs/<jid>/transcript")
def transcript_api(jid):
    f = jpath(jid) / "transcript.json"
    if not f.exists():
        return jsonify({"segments": []})
    t = json.loads(f.read_text())
    return jsonify({"segments": [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in t["segments"]]})


@app.post("/api/jobs/<jid>/clips")
def save_clips(jid):
    job = load(jid)
    data = request.get_json()
    job["clips"] = data.get("clips", job["clips"])
    if "style" in data:
        job["style"].update(data["style"])
    save(job)
    return jsonify(ok=True)


@app.post("/api/jobs/<jid>/render")
def render(jid):
    job = load(jid)
    data = request.get_json(silent=True) or {}
    if "clips" in data:
        job["clips"] = data["clips"]
    if "style" in data:
        job["style"].update(data["style"])
    job.update(status="rendering", progress=0, message="Monteren start")
    save(job)
    threading.Thread(target=render_all, args=(job,), daemon=True).start()
    return jsonify(ok=True)


@app.get("/media/<jid>/<path:name>")
def media(jid, name):
    return send_from_directory(jpath(jid), name, conditional=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5055))
    print(f"\n  Livestream → Reels draait op  http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
