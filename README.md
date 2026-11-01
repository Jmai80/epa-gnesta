# EPA-Gnesta

Ett EPA-traktorspel som utspelar sig i Gnesta i Sörmland. Max 30 km/h, LGF-skylt på bakluckan och Radio Frösjön på.

Spelet körs direkt i webbläsaren och behöver inget byggsteg. Öppna `index.html` via en webbserver, till exempel GitHub Pages.

## Körbara sträckor

- **Storgatan:** Västra Storgatan från Granngården, förbi Elektron och stationen, genom centrum och vidare längs Östra Storgatan under Gnestahöjden och Harsprånget ner mot ån.
- **Tingshusbacken:** från stationen uppför Tingshusgatan, sedan Skolgatan och Frejavägen fram till Frejaskolan.

Resten av samhället syns runt omkring men är avstängt med vägbommar.

## Styrning

| Tangent | Funktion |
|---|---|
| W / ↑ | Gasa |
| S / ↓ | Bromsa / backa |
| A / D | Styra |
| H | Tuta |
| C | Byt kamera (bakom, förare, drönare) |
| I | Visa/dölj hus-ID |
| R | Radio av/på |
| P | Byt lack |
| T | Tillbaka till vägen |
| U | Snabbläge för utveckling: 90 km/h och alla bilvägar öppna |

På mobil och surfplatta visas pekknappar.

## Rätta kartan

Varje hus har ett fast ID (H001, H002 …). Klicka på ett hus eller dess ID-skylt i spelet, tryck **Kopiera ID-rad** och beskriv vad som är fel. Klickar du på marken visas koordinaten för den punkten.

Manuella rättningar (namn, skyltar, färger, specialfasader) ligger i `ANDRINGAR` i `verktyg/bygg_osm.py`. Där är nyckeln husets ID.

## Filer

| Fil | Innehåll |
|---|---|
| `index.html` | Sidan, HUD och styrning |
| `spel.js` | Spelmotorn (terräng, gator, hus, bil, tåg, ljud) |
| `karta.js` | Kartdata, genererad från OpenStreetMap |
| `three.module.js`, `three.core.js` | Three.js (minifierad) |
| `verktyg/bygg_osm.py` | Bygger `karta.js` från en OSM-export |
| `verktyg/data/gnesta.osm` | OpenStreetMap-utdrag över centrala Gnesta |
| `verktyg/data/hus_id.json` | Låser husens ID mellan versioner |

## Bygga om kartan

Kräver Python 3 med `numpy` och `matplotlib`.

```sh
python3 verktyg/bygg_osm.py verktyg/data/gnesta.osm karta.js
```

## Vad är exakt och vad är uppskattat

Gator, husens grundytor, järnvägen, perronger, Frösjöns och Sigtunaåns stränder, torg, parkeringar och markanvändning kommer från OpenStreetMap.

Det här är uppskattat:
- Höjderna: centrum cirka 15 m och Gnestahöjden cirka 60 m vid gamla vattentornet.
- Våningsantal, takformer och färger på de flesta hus.

## Källor och licenser

- Kartdata © [OpenStreetMap](https://www.openstreetmap.org/copyright)-bidragsgivare, tillgänglig under Open Database License (ODbL). `karta.js` och `verktyg/data/gnesta.osm` är härledda från OpenStreetMap och omfattas av ODbL.
- [Three.js](https://threejs.org), MIT-licens (se `THREE-LICENSE.txt`).
