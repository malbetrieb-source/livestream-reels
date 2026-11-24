#!/bin/bash
# Dubbelklik om Livestream → Reels te starten (Mac).
cd "$(dirname "$0")"
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then echo "ffmpeg installeren…"; brew install ffmpeg
  else echo "ffmpeg ontbreekt. Installeer Homebrew (https://brew.sh) en daarna: brew install ffmpeg"; read -n1; exit 1; fi
fi
if [ ! -d .venv ]; then echo "Eerste keer: Python-omgeving opzetten…"; python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q --upgrade pip >/dev/null
pip install -q -r requirements.txt
pip install -q -U yt-dlp   # YouTube verandert vaak; altijd de nieuwste
if [ -f .env ]; then set -a; source .env; set +a; fi
(sleep 2; open "http://127.0.0.1:5055") &
python app.py
