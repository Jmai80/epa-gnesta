# Överlämning: EPA-Gnesta (läget efter utkast 52, 7 nov 2026)

Klistra in eller bifoga den här filen i en ny chatt. Allt som behövs för att fortsätta finns i GitHub-repot **Jmai80/epa-gnesta**.

## 1. Vad projektet är

Ett EPA-traktorspel i webbläsaren (max 30 km/h) som utspelar sig i Gnesta. Kartan byggs från OpenStreetMap och rättas runda för runda efter användarens foton och beskrivningar. Spelet är bara till för vänner, så riktiga företagsnamn och skyltar får användas.

- **Repo:** `Jmai80/epa-gnesta` (publikt, GitHub Pages, troligen `https://jmai80.github.io/epa-gnesta/`, ej verifierat härifrån).
- **Claude-artefakt (privat):** slug `01c7f6c0-bdaf-446f-b006-ca02cd9d5a05`, länk https://claude.ai/artifact/1Dksiut4AjHSBjdyM1ucGL. Den senaste versionen var `1794078885-bfd4`, men hämta alltid aktuell version med `get_artifact` innan du publicerar.
- **Version i spelet:** "utkast 52" står i `index.html` på två ställen: startskärmen och HUD-chippet. Nästa runda blir utkast 53.

## 2. Kom igång i en ny session (cirka 2 minuter)

1. Koppla repot med push-behörighet (`add_repo` owner `Jmai80`, repo `epa-gnesta`, access `push`) och klona det till `/home/claude/epa-gnesta`.
2. Kör `bash /home/claude/epa-gnesta/verktyg/forbered.sh`. Skriptet installerar numpy, matplotlib och shapely, kopierar testskripten till `/home/claude/epa/test` och startar en webbserver för repots rot på port 8772.
3. Kontrollera att allt fungerar:
   `cd /home/claude/epa-gnesta && python3 -I verktyg/bygg_osm.py verktyg/data/gnesta.osm karta.js && node /home/claude/epa/test/fel.js 8772` ska skriva ut `inga fel`. En omgenerering utan ändringar ger byte-identisk `karta.js`.

Jobba direkt i repot. Generatorn hittar `id_v2.json` och höjddata relativt sig själv, och tidigare sökvägar som `/home/claude/osmtools`, `site2` och `distNN` behövs inte längre.

## 3. Rutin för varje runda (användaren förväntar sig den)

1. Gör ändringarna: `verktyg/bygg_osm.py` för kartdata och hus, `spel.js` för hur saker byggs och ritas, och vid behov `index.html`.
2. Generera `karta.js` (kommandot ovan) och kör `fel.js`.
3. Rendera närbilder med `vyer3.js`, titta på dem själv och rätta det som ser fel ut.
4. Räkna upp "utkast N" i `index.html` (`sed -i 's/utkast 52/utkast 53/g' index.html`, men kolla att CSS-kommentaren om Hitta behåller utkast 48).
5. Publicera artefakten med `publish_files` (patch-läge, standard). Ange `slug`, `base_version` från `get_artifact` och bara de ändrade filerna med `as` och `path`, till exempel `index.html`, `karta.js` och `spel.js`.
6. Committa och pusha till `main`:
   - Ta författaren från en tidigare commit: `git log -1 --format='%an <%ae>'` och skicka med den via `-c user.name=… -c user.email=…`.
   - Avsluta commit-meddelandet med de attributionsrader som sessionen anger (Co-Authored-By och Claude-Session).
   - Pushen kan hänga, så kör `timeout 240 git push -q origin HEAD` och kontrollera med `git ls-remote origin refs/heads/main`.
7. **Svara på svenska.** Beskriv kort vad som ändrats och skicka 2–4 renderingar med `SendUserFile`.

## 4. Filer i repot

| Fil | Innehåll |
|---|---|
| `index.html` | UI, HUD, startskärm, ratt och pedaler för mobil, OG-taggar, versionstext |
| `spel.js` (~3600 rader) | Motorn: Three.js r187, terräng, vägar, hus, detaljer, bilar, ljud, kontroller |
| `karta.js` | Genererad data, `window.KARTA = {...}`: hus, gator, ytor, korbar.rutter, terrang, detaljer |
| `three.core.js`, `three.module.js` | **Minifierade.** Byt aldrig mot ominifierade (det hände en gång och fick backas) |
| `mera_bas.mp3` | Låten som Radio Frösjön spelar. Användaren har godkänt att den ligger i det publika repot |
| ikoner, `manifest.webmanifest`, `delning.jpg` | Hemskärmsikon och förhandsbild vid delning (PWA/OG) |
| `verktyg/bygg_osm.py` (~2050 rader) | Generatorn: OSM → `karta.js`, inklusive alla manuella rättningar |
| `verktyg/las.py` | OSM-läsare och projektion. Origo 59.0482 N, 17.3117 E; x = öster, z = söder, i meter |
| `verktyg/id_v2.json` | Fasta hus-ID:n (osm-id → H###), 1711 poster |
| `verktyg/data/gnesta.osm` | Ihopslagen OSM-export (med `sla_ihop.py`) |
| `verktyg/data/topo_hojd.json` | Höjdgrid från topografisk karta (med `topo_dem.py`) |
| `verktyg/test/*.js` | Playwright-test (se avsnitt 7) |
| `verktyg/forbered.sh` | Startskriptet ovan |

## 5. Generatorn (`verktyg/bygg_osm.py`): begrepp och sökord

- **Hus från OSM** skapas i `add_building()`, och klass bestäms av building-taggen (`villa`, `bod`, `radhus`, `flerbostad`, `centrum` och så vidare).
- **`ANDRINGAR["H###"] = {...}`** skriver över attribut per hus-ID. Vanliga nycklar:
  - Form och tak: `typ`, `van`, `fh` (våningshöjd), `rekt`/`poly`, `tak` (sadel/valm/platt/pulpet), `taklutning`, `takfarg`, `takUtsprang`, `takfotFarg`, `takUndersida`.
  - Fasad: `vagg`, `panel`, `tegel` (`True` eller `'gul'`), `utanFonster`, `karmFarg`, `band` (`[{y0, y1, farg}]`).
  - Tillbyggnader och detaljer: `volymer`, `fasadBoxar` (lådor med `x, z, y, b, h, d, rot, farg`, valfritt `rx` och `form` `'cyl'`/`'klot'`), `stanger`, `balkonger`, `rundaTorn`, `ribbor`.
  - Skyltar: `skyltar` (`vid`, `mot`, `text`, `stil`, `hojd`, `hgt`, `bredd`, `bg`, `fg`, `ut`, `utanTak`).
  - Text och märkning: `namn`, `not`, `sakerhet`.
- **`husdel(oid, namn, rekt, poly, attr, txt)`** lägger till egna hus som inte finns i OSM. **Lägg alltid till det nya `oid` i `verktyg/id_v2.json`.** Annars får huset ett ID som kan flytta sig. Nästa lediga ID är **H1724**.
- **`BORTTAGNA`** listar rivna hus, till exempel H015 Godsmagasinet.
- **`lokal(O, U)`** ger `W(u, v)` (punkt), `R(u0, u1, v0, v1)` (rekt) och `P(...)` (polygon) i ett lokalt system: O är ett hörn, U går längs fasaden och V = (-U[1], U[0]). Nästan alla rättningar efter foto bygger på det.
- **`hojdankare.append([x, z, T, R, w])`** lägger en höjdankare: målhöjd T med gaussisk vikt (R ≈ 4–5). Används för att platta till tomter. Hus i sluttning visar annars vägg under sockeln, eftersom golvet läggs på högsta marken.
- **`ytor.append({"typ": ...})`**: `torg`, `parkering` (med `ingaBilar` / `fyllnad`), `plan` (grön), `gras`, `skolgard`, `ljus` (ljus asfalt).
- **Gator:** `gator.append({...})` med `typ` (`path`, `footway`, `cycleway`, …) och `yta` (`gravel` ger grus) och `bil: False`.
- **Körbara rutter** finns i `KARTA["korbar"]["rutter"]`: 0 Storgatan, 1 Tingshusgatan, 2 Nygatan–Skillingagatan, 3 Infart vårdcentralen, 4 Thulegatan–Torggatan, 5 Granbackavägen och 6 Vändplan Granbackavägen (en ring med `utanLyktor`). Rutter byggs av `kedja` (nodlistor).
- **Detaljer** samlas i `KARTA["detaljer"]`:
  - Natur: `storaTrad`, `buskage` (`pts`, `bredd`, `hojd`, `tujor`, `blommor`), `stenblock`, `staket` (stil `'rails'`).
  - Föremål: `cykelstall` (`platser`, `cyklar` `[[plats, färg]]`), `studsmattor`, `sandlador`, `atervinning`, `containrar`, `terrasser`, `beachflaggor`, `vagskyltar`.
  - Bilar: `parkeradeBilar` (`[x, z, vinkel, vikt]`), `fastaBilar` (egen modell och färg, märktext, `reg`) och `parkeringslinjer`.
  - Steget "detaljer flyttade ut från körbanor" flyttar automatiskt buskar och liknande som hamnat på vägar.
- **Fallgrop:** lambdas som fångar loopvariabler binds sent. Fånga värden med standardargument (se `H93_W`).
- Sektionerna hittas med `grep -n "^# ----\|^# ====" verktyg/bygg_osm.py`.

## 6. Motorn (`spel.js`): sökord

- `MOBIL` och `canvasTex`: texturtak, 512 px och 0,26 Mpx på mobil.
- `passaStorlek()`: canvasstorlek, körs varje bildruta och fixade svart halva i liggande läge på iPhone.
- `buildHouses()`: väggar, tak, band och fasadBoxar. `SPECIAL_ONLY` och `buildSpecials()` hanterar specialbyggnader (`vattentorn_gammalt`, `vattentorn_nytt`, `trappa`, `scen`, `station`).
- `bilMallar()`: biltyperna `sedan`, `kombi`, `skap` och `octavia`. Bilarna ritas som InstancedMesh (`bilInst`), högst `ANTAL_BILAR = 150` slumpade, viktade mot närhet till rutterna. Därefter kommer `fastaBilar` med dekaler.
- Detaljbyggare: sök på `DT.sandlador`, `DT.cykelstall`, `DT.studsmattor`, `cykel = (`.
- `initAudio()` och `setRadio()`: motorljud är syntes. Radion spelar `mera_bas.mp3` via MediaElementSource → `rg` → lågpass 14 kHz. Syntradion (`playStep`) är reserv om filen inte laddas (`audio.synt`).
- **Hitta** (`byggVagnat`, `natRutt`, `byggSokindex`, `hittaSok`, `ritaRutt`): vägnät av alla bilvägar, Dijkstra, sökindex och rutten på minikartan. Se utkast 48 nedan.
- `window.__epa` är testkroken: `camAt`, `testStep`, `H`, `world`, `teleport`, `audio`, `setRadio`, `hitta`, `hittaSok`, `valjMal`, `natRutt`, `setSnabb` med flera. Sidan öppnas med `index.html?test`.

## 7. Test och renderingar (`/home/claude/epa/test`, port 8772 som standard)

- `node fel.js 8772`: laddar spelet i 40 s och skriver konsolfel, annars `inga fel`.
- `node vyer3.js PREFIX '[["namn",[kx,kh,kz],[mx,mh,mz]], ...]'`: närbilder från kamera mot mål. Höjderna anges över marken. Bilderna hamnar i `/tmp/epa-bilder/PREFIX_namn.png`. Titta på dem med `Read`. Om solen står bakom motivet blir det motljus (`SOL = (-0.58, 0.46, 0.67)`), så välj kameravinkel därefter.
- `ENHET="iPhone 13" node minne.js 8772`: hörn, heap och texturer som iPhone. Senast 2,18 miljoner hörn, 223 MB heap och 13,9 Mpx. Kraschen förr kom vid 7 miljoner hörn och 148 Mpx. Varna användaren i förväg om något riskerar att dra mycket minne.
- `ENHET=... PRE=... node mobil.js`: mobil-UI, ratt och pedaler.
- `node hitta_test.js` och `node hitta_mobil.js`: sökning, rutter i EPA- och snabbläge, framme-skylten, sökrutan på dator och iPhone (liggande och stående).
- `node autopilot3.js <ruttindex> <sekunder>`: kör en rutt automatiskt.
- `node hojd.js '[["namn",x,z],...]'`: markhöjd i spelet.
- `node radio.js 8772`: kontrollerar att låten spelas, pausas och fortsätter.
- `fordelning.js` och `ogbild.js` (förhandsbild): används sällan.
- Python-snutt för lokala koordinater: `W(u,v) = (O[0]+u*U[0]+v*V[0], O[1]+u*U[1]+v*V[1])` med `V = (-U[1], U[0])`.

## 8. Hur användaren jobbar

- Skriver på svenska och skickar foton med beskrivningar.
- Pekar ut hus med ID från spelets husfakta, till exempel "H1580 (Radhus)", och punkter som "Punkt x=-30, z=70" (klick på marken visar koordinaten).
- Vill ha noggranna detaljer och accepterar extra geometri för påskägg. Säg till innan minnet kan bli ett problem.
- Ändra bara det som efterfrågas. Fråga om något är tvetydigt och dyrt att göra om.
- Bildsökningsverktyget visar bilder för användaren men inte för Claude. Bygg inte på det: be hellre om ett foto. Jag visade av misstag gamla tornet när det nya efterfrågades.

## 9. Vad som är gjort (utdrag, nyast först)

- **Utkast 50: Circle K och rondellen.** Sök på `utkast 50` i generatorn.
  - Rondellen vid Östra Storgatan/Dansutvägen/Nibblegatan (`RONDELL_C`, `RONDELL_R` = 12,5 m till mittlinjen) är ungefär dubbelt så stor. Ringen G337 är en sluten cirkel, de delade körfälten och ringens övriga OSM-delar är borttagna, och tillfarterna kapas eller förlängs till ringen. Rondellön är grus med en ljus kant (`ytor` grus/ljus, låga `hojd` så att inget gräs syns under kanten). Rondellkonsten på användarens foto är ett konstverk och återskapas inte. I stället står där sedan utkast 52 en egen design, en jätteplockepinn: 22 pinnar på 5–7 m i blandade plockepinnfärger som ligger och lutar huller om buller (seed 52). Detaljtypen är `skulpturer`, en lista med lådor, cylindrar och klot kring en fotpunkt. Den ersatte "Röset" från utkast 51 och ska inte göras om till att likna den riktiga skulpturen.
  - Circle K: H046 (OSM "Circle K Gnesta") är butiken: ljusgrå plåt, glasfasad med affischer och röd rand mot rondellen, entrétak, frys och gasolbur. Taket över pumparna är den nya delen H1723 med typen `bensintak` (motorn: i `SPECIAL_ONLY`, ritas bara med fasadlådor och skyltar). Det har röd fris med texten CIRCLE K, två pumpöar, pelare och lysrör. H1318 är tolkad som biltvätten med släpkärror bredvid; användaren har inte bekräftat det. Lokalt system `P46_W/R/P`: u mot SSO, v mot VSV.
  - Ny detalj `prisskyltar` (pylon med namn och pristavla) och `reklamskyltar` med `typ: 'tavla'` (orange gatupratare). Asfaltplan med `ingaBilar` innanför slingan G031/G070. Ingen logga är ritad, bara namnet i vanlig text.
- **Utkast 49: Platåvägen efter två foton till.** Sök på `utkast 49` i generatorn.
  - H736: gavlarna i riktigt rött tegel (`tegelSidor` + nya `tegelSidorRen`, ingen fönstertextur) ner till en låg grå sockel (`band` −3…−1,25) med fyra källarfönster mot Platåvägen, vita vindskivor på båda gavlarna och en parabol vid nocken.
  - H737 lekstugan: grå-blå liggande panel, vita knutar, korrugerat mörkt tak, tvärgavel (1:1) med vita vindskivor över dörren och verandan, vit dörr, spröjsat fönster, trätrall, trappsteg, vitt spjälstaket, vit stol och klätterrosor.
  - 30-skylten: ny vägmärkestyp `hastighet` (`grans`, valfri `bak` = en andra skylt i annan vinkel) med reflexband på stolpen, vid Platåvägens västra kant mitt för lekstugan.
  - Häck längs Nygatan och Platåvägen runt H736/H737 och vitt staket söder om lekstugan. Längs Platåvägen vid H823/H867 en hög häck på en 0,7 m stödmur.
  - H823 "Villa Villekulla": gul panel, brant ockragult plåttak (1:1,15) med gaveln mot Platåvägen, vita knutar, gördelband och vindskivor, vindsfönster, spira, skorsten, burspråk mot norr och svart stålbalkong med utvändig trappa. Nya delar: tvärhuset H1721 (tak 1:1,5, spira) och utbyggnaden H1722 (terrass med svart räcke). Lokalt system `P23_W/R/P`: u söderut längs gaveln, v västerut.
  - H867: ljust trähus i två våningar på grå sockel, låglutande sadeltak med 1 m utsprång (motorn: ny `gavelUtsprang`), ockragula karmar och två vita balkonger mot norr.
- **Utkast 48: namn, Hitta och Platåvägens början.**
  - Granbackavägen 108 heter nu **Samuels hus** (H1605, `adress`, `alias: ["Samuel"]`); "en kompis bor här" är borta. Kadriljvägen 1 heter **Mormor** (H1234 och delarna H1712–H1714, `alias: ["Mormors hus"]`).
  - Hus får `adress` från OSM:s `addr:street`/`addr:housenumber` (48 hus) och visar raden "Adress" i husfakta. `platser` i karta.js: 33 OSM-noder med adress eller namngiven verksamhet.
  - **Hitta** (knapp i HUD:en, tangent F): sökruta med träfflista (husnamn, alias, adresser, platser, gator; å/ä/ö kan skrivas utan prickar). Vägnätet är alla bilvägar, gemensamma punkter slås ihop och lösa ändar inom 12 m kopplas. Rutten räknas om varje halvsekund och ritas blå på minikartan med streckad sista bit till huset, röd nål och pil i kanten. Målskylten sitter ovanför minikartan (till höger om den i liggande mobil) med namn, sträcka och ✕. "Framme vid …!" när det är under 14 m kvar. I EPA-läget används bara den öppna sträckan om målet nås därifrån (Samuels hus gör det), annars visas vägen ändå med texten "Avstängt i EPA-läget – tryck U för snabbläge" (Mormor, Stopp).
  - Platåvägens början efter foto från Nygatan 28 (sök på `Platåvägens början` i generatorn): H736 grå-blå panelvilla med tegelgavlar, vita fönster, vit farstukvist med vimpel och blomampel, skorsten; flygeln på baksidan är ny husdel H1720. H737 lekstugan grå-blå. H751 lågt rött tegelhus med ljust plåttak och upphöjd fönsterrad (motorn: `tegel: 'ren'` = rött tegel utan målade fönster). H789 ljusgult med rött tak. H823 gul villa i två våningar med ljust valmat tak (rekt från OSM-polygonen via `_rekt_lokal`).
  - Kvar: H823 ser ut att ha tre fönsterrader från nedförsbacken eftersom väggen fortsätter ner till lägsta marken. Samma sak med den grå sockeln under H736.
- **Utkast 47:** hälften så många bilar på STOPPs kundparkering (37 st: 16 sedan, 16 kombi, 5 skåpbilar, 10 färger; tröskeln i `_st_bil`). Hastighetsvisaren är 50 % större (`skala`, standard 1,5). **Avgasrök** ur EPA:ns avgasrör (`buildRok`/`updateRok`): 64 partiklar i en `Points`-geometri med egen shader. Ljus rök på tomgång, tätare och mörkare när man gasar. Test: `verktyg/test/rok_test.js`.
- **Utkast 46: STOPP Köpcentrum** (H044) efter foto från Östra Storgatan. Sök på `STOPP Köpcentrum` i generatorn.
  - Lokalt system `ST_W/ST_R/ST_P`: u norrut längs fasaden, v ut mot parkeringen. Klassen `Lador(O, U)` (box, skiva, pinne, fonster) lägger fasadlådor i valfritt lokalt system.
  - Husdelar: H044 mittdelen med Hemköp och skärmtak, H1715 södra (indragen, vitt glasat vindfång, röd skylt), H1716 bakom, H1717 tvåvåningsdelen med skylten STOPP KÖPCENTRUM (stil `tvarad`), H1718 trapphustornet, H1719 norra hallen. Bara entrédelen har två våningar.
  - Marken under köpcentret planas i 15,6 m. Gångytan framför fasaden är 3,6 m bred (`torg`, hojd 0,16) och kundparkeringens framkant följer den. 71 bilar står fast i rader (`fastaBilar` utan text) som på fotot, alltså utöver de 150 slumpade.
  - Skyltarna på övervåningen och den mörka skylten på norra hallen går inte att läsa på fotot och är därför bara färgade fält.
  - **Hastighetsvisaren** vid x=522, z=198 (`detaljer.fartskyltar`, `buildFartskyltar`/`updateFartskyltar`) visar grön glad smiley upp till 40 km/h och blinkande röd arg smiley över. Den mäter bilen när den är framför skylten, inom 90 m och på väg mot den. Test: `verktyg/test/fart_test.js` (kör i snabbläget för 60 km/h).
  - Motorn: `panel: 'ligg'` ger liggande profilplåt.
- **Utkast 45, påskägg Kadriljvägen 1** (H1234, hörntomten vid Menuettvägen, efter två Street View-foton). Sök på `PÅSKÄGG: Kadriljvägen 1` i generatorn.
  - Lokalt system `KD_W/KD_R/KD_P` med origo i husets nordöstra hörn, u österut längs gaveln mot Kadriljvägen, v söderut. Hjälpfunktionerna `kbox`, `kskiva` (lutande skiva), `krör`, `kpinne`, `kklot` och `kfonster` lägger fasadlådor i huvudhusets höjdsystem.
  - Huvudhuset: 1½-plan, gult tegel, vit lockpanel på gavlarna, brant mörkt tak (`taklutning` 0,94), burspråk med valmat plåttak, skorsten, takstege, antenn, hängrännor, gatunamnsskylt "Kadriljvägen" och husnummer.
  - Husdelar: garaget H1712 (vit panel, platt tak, sektionsport, vedbod), tillbyggnaden H1713, entrén H1714 (poly utan rekt) under ett skärmtak.
  - Gården: uppfart i plattor (`torg` med `hojd` 0,12), grusplan (`grus`), soptunnor, brevlåda, släpvagn, tältgarage, båt, flaggstång med vimpel, staket, häckar, elskåp, markeringsstolpe, gatlykta, springcykel och en grå Peugeot kombi (`typ: 'peugeot'`, "KDR 001").
  - Terräng: Menuettvägen plan i 39,4 m från Dansutvägen till Kadriljvägen; Dansutvägen stiger nu ända upp till korsningen (topokartan tonades förut ut mot sin södra kant). Tomten planas i 39,5 m.
  - Motorn: platta tak kan få `kantFarg`/`kantHojd`, ytor kan få egen `hojd`, ny yttyp `grus`, bilmallar kan ha `bakExtra`/`framExtra`/`ljusExtra`.
  - Grannhusen runt Kadriljvägen är fortfarande generiska tre våningar med platta tak (OSM-ytor strax över villagränsen 190 m²); på fotona är det enplansvillor.
- **Utkast 44:** nya vattentornet (H1711, `husdel("vattentorn_nytt")`, `VISA_NYA_TORNET = True`) vid Platåvägen (−1078, 259), 48,7 m ö.h.
  - Läget och diametern på cirka 23 m kommer från OSM-way 71306420.
  - Formen följer användarens foto: vitt, smalt mittskaft, åtta breda ben som går upp som lisener, djup cistern, räcke med antenner och mast med hinderljus.
  - Höjden är förhöjd med `SV = 1.45` (benen cirka 30 m, cisterntopp cirka 46 m, mast 16 m) för att synas över taken vid Granbackavägen. Rakt framför 108 skyms tornet ändå av taket.
  - Radio Frösjön spelar `mera_bas.mp3` (Suno-låt av samuelwalfridsson26, 2:36).
- **Utkast 40–43, påskägg Granbackavägen 108** (H1605, Samuels gavellägenhet längst österut, "Samuels hus" sedan utkast 48):
  - Radhuslängan byggs med `radlanga()`: panel, farstukvistar, dörrar (108 med svart glasspringa), brevlådor, lampor, fönster med persienner, stuprör, antenn och nockräcke.
  - H1580 är en identisk granne med 7 enheter.
  - Mark: plan nivå `GB_MARK = 29.6`.
  - Vid huset: Samuels cykelställ längs fönstret bredvid farstukvisten (framhjulen mot väggen), grön sandlåda efter foto, studsmatta, stenblock.
  - Parkeringen: fyra fickor med en grå Škoda Octavia kombi ("GNS 108") i fickan närmast det allmänna cykelstället.
  - Garagelängorna H1591 och H1601 har platt tak och bruna portar. Förrådet H1607 är kvar.
  - En grusväg mellan låga häckar leder till H1593, ett envåningshus i 108:s färger på en avsats.
  - Grannhusen är i rött tegel med ljust orange tak.
  - Vändplan på Granbackavägen.
- **Utkast 36–39:** buskar längs gångvägen vid (−63, −3), gamla vattentornet (H032, förhöjt 2×), Margretedalsvägen 15 (H385 med torn), Coops lastkaj med buskrad och träd, Gnesta Hem (H194, Thulegatan 3) med G-logga och raka parkeringar.
- **Utkast 34–35:** iPhone-kraschen åtgärdad (InstancedMesh för bilar och texturtak), 150 parkerade bilar, helskärm i liggande läge, Hus-ID-knappen borttagen.
- **Tidigare:** H006 stationshuset med Pressbyrån, H008, H010, H068 vid Thulegatan med fickparkering, ytan där H084 och H113 stod, Bistro Barens uteservering, snedparkeringar (Tingshusgatan vid H092, Torggatan vid scenen), Torggatan 16, Harsprånget (130 steg), ikoner, delningsbild, ratt och pedaler.

## 10. Öppet och möjliga nästa steg

- Vattentornets höjd och proportioner är uppskattade. Fråga om användaren vill ha det högre eller lägre, eller om det ska synas från en viss punkt vid 108.
- Att GitHub Pages har byggt om med `mera_bas.mp3` är inte verifierat. API:t för Pages-byggen är blockerat i den här miljön.
- Inga kända fel i övrigt. Fortsätt med användarens nästa önskemål.

## 11. Fallgropar

- Webbservern på 8772 dör ofta mellan turer. Starta om med `(cd /home/claude/epa-gnesta && python3 -m http.server 8772 >/dev/null 2>&1 &)`.
- Kör generatorn med `python3 -I`.
- Signalen `Shell cwd was reset` betyder att `cd` inte följer med. Använd absoluta sökvägar.
- Använd `deviceScaleFactor: 1` vid emulering, annars tar skärmbilderna lång tid.
- Husgolvet läggs på högsta marken i fotavtrycket. Platta till med höjdankare i sluttningar.
- Hus som är specialbyggda (SPECIAL_ONLY) får inga vanliga väggar. Kollision mot bilen går via `rekt` om det finns, annars via `poly`.
