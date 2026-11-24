# Livestream → Reels

Plak een YouTube-link (of upload een video), geef een briefing mee, en de app:

1. downloadt de stream (yt-dlp)
2. schrijft alles uit met tijdcodes (Whisper, draait lokaal op je Mac)
3. kiest de hoogtepunten — met Claude als er een API-sleutel is, anders op trefwoorden uit de briefing
4. laat je per fragment start/eind, titel, hook en caption bijstellen naast een videospeler en doorzoekbaar transcript
5. monteert verticale 1080×1920 reels met grote ondertitels (actieve woord in accentkleur), hook-tekst in de eerste 3 seconden, genormaliseerd geluid (-14 LUFS), en een .txt met caption per reel

## Starten (Mac)
1. Pak de zip uit, bijvoorbeeld in `Documenten`.
2. Rechtsklik op `start.command` → **Open** (de eerste keer, vanwege macOS-beveiliging).
   De eerste start duurt een paar minuten: Python-omgeving, ffmpeg (via Homebrew) en het spraakmodel worden geïnstalleerd.
3. De app opent op http://127.0.0.1:5055

## Slimmere selectie met Claude
Kopieer `.env.example` naar `.env` en vul `ANTHROPIC_API_KEY` in (console.anthropic.com).
Dan kiest Claude de fragmenten, schrijft hooks en captions, en houdt het rekening met de briefing als geheel.
Zonder sleutel werkt alles ook, maar dan op trefwoorden — controleer dan de grenzen even.

## Tips
- Briefing: één onderwerp per regel met een streepje. In `briefings/` staat die van Remco al klaar (knop "Laad").
- Woordenlijst: zet merk- en productnamen erin, dan spelt de ondertiteling ze goed.
- Beeld: "bijsnijden" voor iemand die praat (schuif de uitsnede naar links/rechts), "heel beeld + vage achtergrond" voor demo's waar het hele shot telt.
- Logo: zet een `logo.png` (transparant) in `assets/`, dan komt het rechtsboven in elke reel.
- Alles van een stream staat in `werkmap/<datum>/`; de reels in de submap `reels/`.
