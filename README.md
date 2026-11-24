# Livestream → Reels

Maakt van een YouTube-livestream automatisch verticale reels (1080×1920) met grote ondertitels, een hook in beeld en een caption per reel.

## Zo gebruik je het (alleen je browser nodig)
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
