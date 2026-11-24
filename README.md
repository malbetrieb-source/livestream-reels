# Livestream → Reels

Maakt van een YouTube-livestream automatisch verticale reels (1080×1920) met grote ondertitels, een hook in beeld en een caption per reel.

## De app (aanrader)
**https://malbetrieb-source.github.io/livestream-reels/** — werkt op telefoon en laptop.

Link plakken, voicenote inspreken of bestand kiezen (bv. die van Remco), op *Maak reels* drukken. De app toont de voortgang, daarna per reel een preview, hook, caption (kopieerknop) en begin/eind. Bijstellen → *Opnieuw maken*: dat gaat in een paar minuten, omdat download en transcript uit de cache komen.

**Eenmalig:** *Settings → Pages →* Source *Deploy from a branch*, branch `main`, map `/docs` → Save. Maak daarna in de app bij *Instellingen* een fine-grained token aan (alleen deze repo; Actions + Contents: Read and write).

**Zonder Anthropic-sleutel:** op de resultaatpagina staat *Slimmer kiezen met Claude*: kopieer de opdracht, plak hem in een chat met Claude, plak het antwoord terug en klik *Overnemen* → *Opnieuw maken*.

Hoe het werkt: de app zet de voicenote op een branch `reels/<aanvraag>`, start de workflow, en de workflow zet daar na afloop de previews (720p), captions en `resultaat.json` neer (de voicenote zelf verdwijnt dan van die branch). Oude aanvragen opruimen = de branch `reels/…` verwijderen.

## Zonder app (alleen GitHub)
1. Ga in deze repo naar **Actions** → **Maak reels van livestream** → **Run workflow**.
2. Plak de YouTube-link, kies eventueel aantal/lengte, en klik op de groene **Run workflow**.
3. Wacht tot het bolletje groen is (ongeveer 20–40 min bij een stream van een uur).
4. Klik op de run: bovenaan staat een overzicht van alle reels met tijdcodes, onderaan onder **Artifacts** de zip met de mp4's en captions.

**Een fragment net anders?** Start opnieuw met dezelfde link en vul bij *fragmenten* de tijden in, bv. `12:05-12:48 Combi-Fix diepte; 1:02:10-1:02:55 Boren`. Download en transcriptie komen dan uit de cache: klaar in een paar minuten.

## Eenmalig instellen (aanrader)
**Settings → Secrets and variables → Actions → New repository secret**
- `ANTHROPIC_API_KEY`: hiermee kiest Claude de hoogtepunten en schrijft hooks en captions. Zonder sleutel wordt er gezocht op trefwoorden uit de briefing.

## Aanpassen zonder code
- `briefings/`: briefing per stream, één onderwerp per regel met een streepje. Nieuwe toevoegen via *Add file → Create new file*.
- `woordenlijst.txt`: merk- en productnamen, zodat de ondertiteling ze goed spelt.
- `assets/logo.png`: zet hier een transparant logo neer, dan komt het rechtsboven in elke reel.

## Lokaal draaien (optioneel)
`start.command` (Mac) start een webversie waarin je fragmenten met een videospeler kunt bijstellen. Zie LEESMIJ.md.
