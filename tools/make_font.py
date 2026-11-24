"""Maakt een vast ExtraBold-lettertype (Kumbh Sans, lijkt op Borgh's Gibson) voor de ondertitels."""
import sys, urllib.request
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
URL = "https://github.com/google/fonts/raw/main/ofl/kumbhsans/KumbhSans%5BYOPQ,wght%5D.ttf"
out = sys.argv[1] if len(sys.argv) > 1 else "assets/BorghSub.ttf"
urllib.request.urlretrieve(URL, "/tmp/ks.ttf")
f = TTFont("/tmp/ks.ttf")
loc = {a.axisTag: (800 if a.axisTag == "wght" else a.defaultValue) for a in f["fvar"].axes}
s = instancer.instantiateVariableFont(f, loc)
for rec in s["name"].names:
    if rec.nameID in (1, 4, 16):
        rec.string = "Borgh Sub"
    elif rec.nameID in (2, 17):
        rec.string = "Regular"
    elif rec.nameID == 6:
        rec.string = "BorghSub-Regular"
s.save(out)
print("lettertype gemaakt:", out)
