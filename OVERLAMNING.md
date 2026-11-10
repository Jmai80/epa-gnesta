# Överlämning: EPA-Gnesta (läget efter utkast 57, 10 nov 2026)

Bifoga den här filen i en ny chatt, eller klistra in den. Allt annat som behövs finns i GitHub-repot **Jmai80/epa-gnesta**, och den här filen ligger också där som `OVERLAMNING.md`.

> **Förslag på första meddelande i nästa chatt:**
> "Vi fortsätter med EPA-Gnesta. Läs OVERLAMNING.md (bifogad, finns också i repot Jmai80/epa-gnesta), koppla repot med push-behörighet, kör verktyg/forbered.sh och bekräfta att generatorn och fel.js går igenom. Svara på svenska. Sedan skickar jag nästa foto."

---

## 1. Vad projektet är

EPA-Gnesta är ett EPA-traktorspel i webbläsaren (max 30 km/h, snabbläge finns) som utspelar sig i Gnesta. Kartan byggs från OpenStreetMap. Varje runda skickar användaren Street View-foton, hus-ID:n och beskrivningar, och spelet rättas efter dem. Spelet är bara till för vänner, så riktiga företagsnamn och skyltar får användas. Loggor ritas dock inte, bara namnen i vanlig text.

- **Repo:** `Jmai80/epa-gnesta` (publikt, gren `main`, GitHub Pages, troligen `https://jmai80.github.io/epa-gnesta/`, ej verifierat härifrån). Senaste commit: `cf39d63` (utkast 57), pushad och kontrollerad med `git ls-remote`.
- **Claude-artefakt (privat):** slug `01c7f6c0-bdaf-446f-b006-ca02cd9d5a05`, länk https://claude.ai/artifact/1Dksiut4AjHSBjdyM1ucGL. Senaste versionen är `1794175369-5d58` (utkast 57). Hämta ändå alltid aktuell version med `get_artifact` innan du publicerar. Läsläget är `owner`, så `shared_live` ska utelämnas.
- **Version i spelet:** "utkast 57" står i `index.html` på två ställen: startskärmen (`utkast 57 · `) och HUD-chippet (`<span class="v">utkast 57</span>`). Nästa runda blir **utkast 58**.

## 2. Kom igång i en ny session (cirka 2 minuter)

1. Koppla repot med push-behörighet (`add_repo` owner `Jmai80`, repo `epa-gnesta`, access `push`), klona det till `/home/claude/epa-gnesta` och anropa `register_repo_root`.
2. Kör `bash /home/claude/epa-gnesta/verktyg/forbered.sh`. Skriptet:
   - installerar numpy, matplotlib och shapely;
   - kopierar testskripten till `/home/claude/epa/test`;
   - startar en webbserver för repots rot på port 8772.
   Testskripten går också att köra direkt från `verktyg/test/` i repot.
3. Kontrollera att allt fungerar:
   ```
   cd /home/claude/epa-gnesta && python3 -I verktyg/bygg_osm.py verktyg/data/gnesta.osm karta.js && node verktyg/test/fel.js 8772
   ```
   Det ska sluta med `skrev karta.js 2149 kB` och `inga fel`. En omgenerering utan ändringar ger en byte-identisk `karta.js`.

Jobba direkt i repot. Generatorn hittar `id_v2.json` och höjddata relativt sig själv. Gamla sökvägar som `/home/claude/osmtools`, `site2` och `distNN` behövs inte längre.

## 3. Rutin för varje runda (användaren förväntar sig den)

1. **Gör ändringarna:** `verktyg/bygg_osm.py` för kartdata och hus, `spel.js` för hur saker byggs och ritas, och vid behov `index.html`.
2. **Generera och felkolla:** kör generatorn (kommandot ovan) och `node verktyg/test/fel.js 8772`.
3. **Rendera och granska:** gör närbilder med `vyer3.js` (avsnitt 8), titta på dem själv med `Read` och rätta det som ser fel ut. Skicka aldrig bilder du inte har tittat på.
4. **Kolla minnet** med `minne.js` om rundan lade till mycket geometri eller många texturer.
5. **Räkna upp versionen:**
   ```
   sed -i 's/utkast 57 · /utkast 58 · /; s/<span class="v">utkast 57<\/span>/<span class="v">utkast 58<\/span>/' index.html
   ```
   Kontrollera med `grep -c "utkast 58" index.html` (ska ge 2). CSS-kommentaren "Hitta (utkast 48)" ska vara kvar som den är.
6. **Uppdatera den här filen:**
   - rubriken;
   - artefaktversionen och utkastnumret i avsnitt 1;
   - sed-raden ovan;
   - nästa lediga hus-ID;
   - en ny punkt överst i avsnitt 11 ("Vad som är gjort");
   - avsnitt 12 ("Öppet").
7. **Publicera artefakten:** först `get_artifact`, sedan `publish_files` i patch-läge (standard) med `slug`, `base_version` och bara de ändrade filerna (`as` + `path`, till exempel `index.html`, `spel.js`, `karta.js`), plus `label: "utkast N"`. Lägg sedan in den nya versionen i avsnitt 1 (`sed -i 's/GAMMAL/NY/' OVERLAMNING.md`).
8. **Committa och pusha till `main`:**
   - Författaren i de senaste commitarna är `Claude <noreply@anthropic.com>` (kolla med `git log -1 --format='%an <%ae>'`).
   - Avsluta commit-meddelandet med de attributionsrader som sessionen anger (Co-Authored-By och Claude-Session).
   - Pushen kan hänga. Kör `timeout 240 git push -q origin HEAD` och kontrollera sedan att `git ls-remote origin refs/heads/main` ger samma hash som `git rev-parse HEAD`.
9. **Svara på svenska.** Beskriv kort vad som ändrats, vad som är antaget och vad som är öppet, och skicka 2–4 renderingar med `SendUserFile`. Renderingar som tas före versionsbytet visar förra utkastnumret i hörnet. Det går bra, men nämn det i bildtexten.

## 4. Filer i repot

| Fil | Innehåll |
|---|---|
| `index.html` (~320 rader) | UI, HUD, startskärm, Hitta-panelen, ratt och pedaler för mobil, OG-taggar, versionstext |
| `spel.js` (~4000 rader) | Motorn: Three.js r187, terräng, vägar, hus, detaljer, bilar, ljud, kontroller, Hitta |
| `karta.js` (~2,1 MB) | Genererad data, `export const KARTA = {...}`: hus (1720), gator (615), ytor, korbar.rutter, terrang, detaljer, platser (33) |
| `three.core.js`, `three.module.js` | **Minifierade.** Byt aldrig mot ominifierade versioner (det hände en gång och fick backas). |
| `mera_bas.mp3` | Låten som Radio Frösjön spelar. Användaren har godkänt att den ligger i det publika repot. |
| ikoner, `manifest.webmanifest`, `delning.jpg` | Hemskärmsikon och förhandsbild vid delning (PWA/OG) |
| `verktyg/bygg_osm.py` (~3200 rader) | Generatorn: OSM → `karta.js`, inklusive alla manuella rättningar |
| `verktyg/las.py` | OSM-läsare och projektion. Origo 59.0482 N, 17.3117 E; x = öster, z = **söder**, i meter |
| `verktyg/id_v2.json` | Fasta hus-ID:n (osm-id eller eget oid → H###), 1723 poster |
| `verktyg/data/gnesta.osm` | Ihopslagen OSM-export (gjord med `sla_ihop.py`) |
| `verktyg/data/topo_hojd.json` | Höjdgrid från topografisk karta (gjord med `topo_dem.py`) |
| `verktyg/test/*.js` | Playwright-test (avsnitt 8) |
| `verktyg/forbered.sh` | Startskriptet ovan |
| `OVERLAMNING.md` | Den här filen |

## 5. Koordinater och rotationer (läs innan du placerar något)

- **x är öster och z är söder.** Större z ligger alltså längre söderut. "Norra sidan" av något har mindre z.
- **Hus-ID och punkter:** användaren klickar i spelet och skriver till exempel "H326 (Flerbostadshus)" eller "Punkt x=-389, z=171". Läs husets polygon ur `karta.js` (`KARTA.hus.find(h => h.id === 'H326')`).
- **`M4(x, y, z, ry, sx, sy, sz, rx, rz)`** i motorn använder Euler-ordningen YXZ.
  - Yaw `r`: lokal x pekar mot `(cos r, −sin r)` och lokal z mot `(sin r, cos r)`.
  - Positivt `rx` tippar lokal +z nedåt, och en cylinders topp (lokal +y) åt lokal +z.
- **Skyltar och plan som ska vända framsidan mot riktningen (dx, dz):** `rot = atan2(dx, dz)`.
- **Bänkar** (`bankar`) har ryggen på lokal +z. En bänk som ska vända sig mot (dx, dz) får `rot = atan2(−dx, −dz)`.
- **Bollplanens `rot`** är långaxelns riktning, `atan2(dx, dz)`.
- **`lokal(O, U)`** ger `W(u, v)` (punkt), `R(u0, u1, v0, v1)` (rekt) och `P(...)` (polygon). O är ett hörn, U går längs fasaden och V = (−U[1], U[0]).
  - Om polygonens hörn går medsols i x/z-planet (som OSM-husen här brukar göra), pekar V **in** i huset när U följer kanten. Negativt v är då utanför fasaden; balkonger ligger till exempel på v ≈ −0,7.
  - Kontrollera riktningen med en rendering om du är osäker.
- **Höjder:**
  - `fasadBoxar` har y i förhållande till husets golv g0, och lådan ritas med centrum på y + h/2.
  - g0 = (`sutterang` ? lägsta mark + 0,25 : min(högsta mark, lägsta mark + 4) + 0,25) + (`golvLyft` || 0).
  - Skulpturdelar har y i förhållande till marken vid skulpturens fotpunkt, plus `lyft`; centrum ligger på y + h/2.

## 6. Generatorn (`verktyg/bygg_osm.py`)

### 6.1 Karta över filen (ungefärliga radnummer)

| Rad | Innehåll |
|---|---|
| ~311 | Ytor från OSM (torg, parkering, plan, lekplats, bryggor) |
| ~377 | Rondellen vid Circle K (`RONDELL_C`, `RONDELL_R`) |
| ~425 | `RUTTER = [...]`, de körbara sträckorna i EPA-läget |
| ~532 | Byggnader: `add_building()`, och `lokal()` (~797) och `husdel()` (~806) |
| ~1051 | `ANDRINGAR = {...}`, äldre rättningar per hus |
| ~1775 | `class Lador`, fasadlådor i valfritt lokalt system |
| ~1864–2245 | Fotorundor: Platåvägen (48–49), Circle K (50), backen vid Ringvägen (53), Torggatan 17–25 (54), Torggatans norra sida (56), H326 (57) |
| ~2247 | `for h in hus: if h["id"] in ANDRINGAR: h.update(...)`. **Nya husrättningar läggs precis före den här raden.** |
| ~2304 | Höjder från topografisk karta och `hojdankare` |
| ~2827 | `PLATSER` (sökbara platser för Hitta) |
| ~2842 | `KARTA = {...}` med standardlistorna för `detaljer` |
| ~2982–3130 | Detaljer per runda: Circle K, plockepinnen, backen (53), H277:s höjdankare, Thuleparken (57). **Nya detaljblock läggs före `print("Platåvägen: häckar" ...)`.** |
| ~3133 | Kontroll: buskar, staket, bänkar, papperskorgar med mera flyttas automatiskt ut från **bilvägar** (inte gångvägar) |
| slutet | Skriver `karta.js` |

Hitta sektionerna med `grep -n "^# ----\|^# ====\|^# --- " verktyg/bygg_osm.py`, och en viss runda med till exempel `grep -n "utkast 57" verktyg/bygg_osm.py`.

### 6.2 Hus

- **Hus från OSM** skapas i `add_building()`. Klassen bestäms av building-taggen (`villa`, `bod`, `radhus`, `flerbostad`, `centrum` och så vidare).
- **`ANDRINGAR["H###"] = {...}`** skriver över attribut per hus-ID. Vanliga nycklar:
  - Form och tak: `typ`, `van` (våningar), `fh` (våningshöjd), `rekt`/`poly`, `tak` (`sadel`/`valm`/`platt`/`pulpet`), `taklutning`, `takfarg`, `takUtsprang`, `takfotFarg`, `takUndersida`, `gavelUtsprang` (standard 0,45), `kantFarg`/`kantHojd` (takkant på platta tak).
  - Fasad: `vagg`, `panel` (`True` eller `'ligg'`), `tegel` (`True`, `'gul'`, `'ren'` = rött utan målade fönster, `'brun'` = orangebrunt med fönster, `'beige'`), `tegelSidor`, `tegelSidorRen`, `utanFonster`, `karmFarg`, `band` (`[{y0, y1, farg}]`, y relativt g0, negativt = sockel), `lisener`.
  - Mark och golv: `sutterang: True` lägger golvet efter lägsta marken. `golvLyft` (meter) höjer golvet; ihop med ett mörkt `band` ger det en synlig sockelvåning.
  - Tillbyggnader och detaljer: `volymer`, `fasadBoxar`, `stanger`, `balkonger`, `rundaTorn`, `ribbor`.
  - Skyltar: `skyltar` (`vid`, `mot`, `text`, `stil`, `hojd`, `hgt`, `bredd`, `bg`, `fg`, `ut`, `utanTak`, `kursiv`).
  - Text och märkning: `namn`, `alias`, `adress`, `not`, `sakerhet` (`osm`/`foto`).
- **`class Lador(O, U)`** lägger fasadlådor i ett lokalt system (u längs U, v längs V) och samlar dem i `.lista`, som blir `fasadBoxar`.
  - `box(u, v, y, b, h, d, farg, a=0, rx=0, form=None)`: lokal x längs vinkeln a i u→v-planet. `form` kan vara `'cyl'`, `'klot'` eller `'gavel'` (trekantigt prisma med nocken längs d).
  - `skiva(u, v, yc, bredd, langd, tjock, farg, fall, lut)`: lutande takskiva.
  - `pinne(u, v, y0, y1, diam, farg)`: stående cylinder.
  - `fonster(u, v, n, w, h, yb, karm, glas)`: fönster.
  - Exempel: `_balkong326` (utkast 57) lägger en Lador per fasadkant och staplar inglasade balkonger.
- **`husdel(oid, namn, rekt, poly, attr, txt)`** lägger till egna hus som inte finns i OSM. **Lägg alltid till det nya `oid` i `verktyg/id_v2.json`**, annars får huset ett ID som kan flytta sig. Senaste är `circlek_tak` = H1723. **Nästa lediga ID är H1724.** `_hus_id` mappar osm-id till hus, så att fasadlådor och skyltar kan sättas direkt på husdelar.
- **`BORTTAGNA`** listar rivna hus, till exempel H015 Godsmagasinet.
- **`_torghus(hid, nummer)`** (utkast 54) är ett exempel på en funktion som bygger flera likadana hus.

### 6.3 Mark, ytor, vägar

- **`hojdankare.append([x, z, T, R, w])`** lägger en höjdankare: målhöjd T med gaussisk vikt (R ≈ 4–15). Används för att platta till tomter. Hus i sluttning visar annars vägg under sockeln.
- **`KARTA["ytor"]`** har typerna `torg`, `parkering` (med `ingaBilar` / `fyllnad`), `plan` (grön, 0,06 över mark), `lekplats` (sand, 0,07), `gras`, `grus`, `ljus` (ljus asfalt), `skolgard`, `brygga` och `fontan`. Ytor kan ha egen `hojd`.
  - Slumpade träd undviker alla ytor utom `lekplats`.
  - En yta som ligger under ett platt föremål kan sticka upp genom det. Ta bort ytan (som `plan` under bollplanen i utkast 57).
- **Gator:** `gator.append({...})` med `typ` (`path`, `footway`, `cycleway`, …), `yta` (`gravel` ger grus) och `bil: False`.
- **Körbara rutter** (EPA-läget kör bara på dem) finns i `RUTTER` → `KARTA["korbar"]["rutter"]`: Storgatan, Tingshusgatan, Nygatan–Skillingagatan, Infart vårdcentralen, Thulegatan–Torggatan, Granbackavägen, Torggatan väster, tre delar av Platåvägen och Vändplan Granbackavägen (en ring med `utanLyktor`).
  - Rutterna byggs av `ways` eller `kedja` (nodlistor, `_nod_kedja`), med `oppenSlut` vid behov.
  - Sidogator som inte är rutter får bommar (stumpar) i EPA-läget.
- **`PLATSER`** är sökbara platser: OSM-noder med adress eller namngiven verksamhet (till exempel "Thuleparken" vid (−358,5; 180,7)).

### 6.4 Detaljer (`KARTA["detaljer"]`)

- **Natur:** `storaTrad` (`x, z, h, r`), `buskage` (`pts`, `bredd`, `hojd`, `tujor`, `blommor`), `stenblock`, `berg`, `tradfritt` (polygoner där inga slumpade träd växer), `rabatter`.
- **Gatumöbler:**
  - `bankar` (`x, z, rot, farg`), `picknickbord` (`x, z, rot`), `papperskorgar` (`x, z`);
  - `flaggstanger` (`x, z, h, flagga`), `brevlador`, `krukvaxter`;
  - `staket` (stil `'rails'`), `stodmurar` (`gata, fran, till, sida, hojd`).
- **Skyltar:**
  - `vagskyltar` (`x, z, rot, typ`), där typ är `'P'`, `'hastighet'` (`grans`, `bak`), `'gangCykel'` eller `'forbudInfart'`;
  - `overgangar` (`osm`, `nara`, valfritt `trafikljus`, `refug`, `skyltar` `[{typ, sida, ds}]`), som ger ett övergångsställe med skyltar;
  - `reklamskyltar` (`typ: 'tavla'`/`'glass'`), `prisskyltar` (pylon med pristavla), `gatupratare`, `anslagspelare`, `skyltstall`, `fartskyltar` (hastighetsvisaren).
- **Park (utkast 57):**
  - `bollplaner` (`x, z, rot, L, B, staket, sarg`): konstgräs med linjer, brun sarg, nätstängsel och små mål med nät.
  - `stenskyltar` (`x, z, rot, text, b, h, d`): betongblock med gult namnfält.
- **`skulpturer`** (`namn, x, z, lyft, tradR, delar[]`), där delar är `{form: 'cyl'|'klot'|'gavel'|låda, x, y, z, b, h, d, rot, rx, farg}`. Används för plockepinnen, lekredskapen, bajamajan och pollarna.
  - Generatorns hjälpklass **`_Grupp(x, z, r)`** har metoderna `box(lx, y, lz, ...)`, `stang(p0, p1, diam, farg)` (cylinder eller fyrkantsrör mellan två lokala punkter), `planka(p0, p1, b, t, farg)`, `W(lx, lz)` och `ut(namn, tradR)`.
  - `tradR` (standard 9 m) är radien som hålls fri från slumpade träd.
- **Föremål:** `cykelstall`, `studsmattor`, `sandlador` (glasfiberlåda med lock), `atervinning`, `containrar`, `terrasser`, `serveringar`, `beachflaggor`, `uteplatser`, `dorrar`, `skorstenar`, `gangtunnlar`.
- **Bilar:** `parkeradeBilar` (`[x, z, vinkel, vikt]`), `fastaBilar` (egen modell och färg, märktext, `reg`) och `parkeringslinjer`.
- **Kontrollera placeringar:** kopiera `_vagkant(x, z)` från Thuleparken-blocket. Den ger avståndet till närmaste väg- eller gångvägskant (inklusive trottoar), och generatorn skriver ut det. Automatiken i slutet flyttar bara ut saker från bilvägar.

### 6.5 Fallgrop i Python

Lambdas som fångar loopvariabler binds sent. Fånga värden med standardargument (se `H93_W`).

## 7. Motorn (`spel.js`): sökord

- **Textur och skärm:**
  - `MOBIL` och `canvasTex(w, h, draw, srgb = true, repeat = true)`: texturtak (512 px och 0,26 Mpx på mobil). `repeat = false` ger klämda kanter.
  - `textTex` och `smaSkyltTex(sk, w, hgt)`: skyltar under 2 m ritas i 512 px och delar textur via `_skyltCache`.
  - `passaStorlek()`: canvasstorlek. Den körs varje bildruta och fixade svart halva i liggande läge på iPhone.
- **Hus:**
  - `buildHouses()` bygger väggar, tak, band och fasadBoxar.
  - `gavelGeo(b, h, d)` är det trekantiga prismat.
  - `tegelMB` väljer tegeltextur (`tegelRen`, `tegelBrun`, `tegelBeige` med flera).
  - `SPECIAL_ONLY` och `buildSpecials()` hanterar specialbyggnader (`vattentorn_gammalt`, `vattentorn_nytt`, `trappa`, `scen`, `station`, `bensintak`).
- **Detaljer:** detaljbyggarna ligger efter varandra runt rad 2150–2500. Sök på `DT.bankar`, `DT.bollplaner`, `DT.stenskyltar`, `DT.skulpturer`, `DT.prisskyltar`, `DT.vagskyltar`, `DT.overgangar`, `DT.sandlador` med flera. Små delar bakas ihop till en mesh (`parts.push({ g, m: M4(...), c: C(färg) })`). Texturerade plan blir egna meshar via `scene.add`.
- **Träd:** `buildTrees()` (cirka rad 3100) använder ett beläggningsgrid med `mark(x, z, r)` och `markPoly(poly, pad)`. **En ny detaljtyp som inte ska ha träd i sig måste läggas till där.**
- **Bilar:** `bilMallar()` har biltyperna `sedan`, `kombi`, `skap`, `octavia` och `peugeot`. Bilarna ritas som InstancedMesh (`bilInst`), högst `ANTAL_BILAR = 150` slumpade och viktade mot närhet till rutterna. Därefter ritas `fastaBilar` med dekaler.
- **Ljud:** `initAudio()` och `setRadio()`. Motorljudet är syntes. Radion spelar `mera_bas.mp3` via MediaElementSource → `rg` → lågpass 14 kHz. Syntradion (`playStep`) är reserv om filen inte laddas.
- **Hitta:** `byggVagnat`, `natDijkstra`, `natRutt`, `byggSokindex`, `hittaSok`, `ritaRutt`, `updateHitta`, med tangenten F. Se utkast 48 i avsnitt 11.
- **Avgasrök:** `buildRok`/`updateRok`.
- **Hastighetsvisaren:** `buildFartskyltar`/`updateFartskyltar`.
- **Testkroken `window.__epa`** öppnas med `index.html?test` och har bland annat `camAt`, `testStep`, `H` (markhöjd), `world`, `teleport`, `car` (riktningen heter `h`), `audio`, `setRadio`, `hitta`, `hittaSok`, `valjMal`, `natRutt` och `setSnabb`.

## 8. Test och renderingar (port 8772 som standard)

Kör från `verktyg/test/` i repot eller från `/home/claude/epa/test`.

- `node fel.js 8772` laddar spelet i 40 s och skriver ut konsolfel, annars `inga fel`.
- `UT=/tmp/epa-bilder node vyer3.js PREFIX '[["namn",[kx,kh,kz],[mx,mh,mz]], ...]'` ger närbilder från kamera mot mål. Höjderna anges över marken. Bilderna hamnar i `/tmp/epa-bilder/PREFIX_namn.png`; titta på dem med `Read`.
  - Om solen står bakom motivet blir det motljus (`SOL = (-0.58, 0.46, 0.67)`).
  - Kameran kan hamna inuti ett träd, så flytta den då.
  - Exempel från utkast 57: `[["entre",[-408,1.7,156],[-382,2,170]],["hus",[-400,1.7,138],[-362,6,118]],["ovan",[-420,45,120],[-372,0,170]]]`.
- `ENHET="iPhone 13 landscape" node minne.js 8772` mäter hörn, heap och texturer som på iPhone.
  - Efter utkast 57: **2,53 M hörn, 1577 meshar, heap 190 MB (topp 295), 16,6 Mpx texturer.**
  - Kraschen förr kom vid 7 M hörn och 148 Mpx.
  - Varna användaren i förväg om något riskerar att dra mycket minne.
- `node hojd.js '[["namn",x,z],...]'` ger markhöjden i spelet. Thuleparken är plan, 14,15 m.
- `ENHET=... PRE=... node mobil.js` testar mobil-UI, ratt och pedaler.
- `node hitta_test.js` och `node hitta_mobil.js` testar sökning, rutter i EPA- och snabbläget, framme-skylten och sökrutan på dator och iPhone.
- `node bom_test.js` kör på Torggatan och Platåvägen (utkast 55). `node ck_rutt.js` kör vid Circle K och rondellen.
- `node autopilot3.js <ruttindex> <sekunder>` kör en rutt automatiskt.
- `node radio.js 8772`, `fart_test.js`, `rok_test.js`, `fordelning.js` och `ogbild.js` (förhandsbilden) används sällan.

## 9. Hur användaren jobbar och vad hen vill

- Skriver på svenska och skickar foton med beskrivningar. **Svara alltid på svenska.**
- Pekar ut hus med ID från spelets husfakta ("H1580 (Radhus)") och punkter ("Punkt x=-30, z=70"; ett klick på marken visar koordinaten).
- Vill ha noggranna detaljer och accepterar extra geometri för påskägg. Säg till innan minnet kan bli ett problem (iPhone har kraschat förut).
- **Ändra bara det som efterfrågas. Fråga om något är tvetydigt och dyrt att göra om.** Förbättringar som ingen bett om kan erbjudas i en mening (till exempel mansardtak på H347), men görs inte.
- **Beskriv exakt vad som är byggt.** När jag kallade en sluten form för pinnar svarade användaren "lögn". Säg hellre vad som är antaget eller påhittat (som lekredskapens placering i Thuleparken).
- **Konstverk återskapas inte**, inte heller rondellskulpturen. Användaren gick med på en egen design (jätteplockepinnen, utkast 52) men var mycket missnöjd med de tidigare försöken ("bottenbetyg"). Gör inte om den till att likna originalet. Byggnader, butiksfasader och skyltnamn går bra, men inga loggor.
- Bildsökningsverktyget visar bilder för användaren men inte för Claude. Bygg inte på det; be om ett foto. (Jag visade av misstag gamla vattentornet när det nya efterfrågades.)
- Användarens e-postadress är privat. Den används bara för att identifiera användaren och skickas aldrig till någon tjänst.

## 10. Läget i Thuleparken (senaste rundan, så att nästa runda kan bygga vidare)

- **Bollplanen** har centrum (−384,55; 176,95), `rot` −0,097, 37,0 × 20,9 m (OSM-planen minus 0,3 m), sarg 1,0 m och staket 4,0 m.
- **Gångvägar runt parken:**
  - G196 längs norra sidan av planen och vidare österut;
  - G446 mellan Thulegatan och planen;
  - G604 söder om planen;
  - G249 i nord–sydlig riktning öster om lekplatsen.
- **Thulegatan** är G043 (OSM-väg 41556702). Övergångsstället ligger vid (−403,2; 158).
- **Entrén:**
  - stenskylten "Thuleparken" vid (−400,5; 163,7);
  - bajamajan vid (−392,4; 151,2);
  - pollarna vid x ≈ −399,6, z 157,6–159,8;
  - P-skylten vid (−399,1; 154,7), med framsidan mot väster.
- **Lekplatsen:**
  - gungorna vid (−362,5; 178);
  - lektornet vid (−360,5; 191), med fjädergungor och sandlåda bredvid;
  - fågelbogungan vid (−333,5; 186).
- **Träd:** `tradfritt` har två polygoner, en för gräsmattan mellan H326 och G196 och en för lekytan öster om planen. Fem `storaTrad` står runt dem.
- **H326** har polygonen `H326_POLY` i generatorn. Balkonger sitter på kanterna 1, 3, 4 och 6 (södra och västra sidorna), med 2, 2, 1 och 3 staplar på fyra våningar.

## 11. Vad som är gjort (utdrag, nyast först)

- **Utkast 57: Thuleparken och H326** (foton från övergångsstället på Thulegatan vid planen och från Thulegatan 6). Sök på `utkast 57` i generatorn.
  - Bollplanen ligger på OSM-planens plats (37 × 21 m). Den har konstgräs med vita linjer, låg brun sarg, 4 m högt nätstängsel på stolpar och små mål med nät i kortändarna. OSM-ytan `plan` under den är borttagen.
  - Entrén vid övergångsstället har ett betongblock med gul skylt "Thuleparken", en grå bajamaja, en papperskorg, tre svarta pollare med gula band i gångvägens mynning, ett övergångsställe över Thulegatan och en P-skylt.
  - De stora sandfärgade lekplatsytorna från OSM är borttagna. Runt planen finns nu öppen gräsmatta (`tradfritt`) mot H326 med några stora träd, bänkar, papperskorgar och två picknickbord. Öster om planen ligger en lekplats med gungor, ett lektorn med rött tak och gul rutschkana, två fjädergungor och en sandlåda, och på andra sidan gångvägen en fågelbogunga. Under redskapen ligger små sandytor. **Lekredskapens och P-skyltens placering är påhittad**, eftersom fotot bara visar planen.
  - H326 har fyra våningar i ljust beige puts över en mörkgrå sockelvåning (`golvLyft` 1,6), platt tak och staplade inglasade balkonger med vita ramar på södra och västra sidorna.
  - Motorn har nya `bollplaner` och `stenskyltar`, `form: 'gavel'` i skulpturer, `tradR` på skulpturer och tunnare cylindrar (8 segment under 0,2 m).
- **Utkast 56: Torggatans norra sida** (foton från Torggatan 17 och 21).
  - H269 är 100 m långt, ljust gult, med tre våningar och en fjärde i mansardtak. Mansarden består av fasadlådor: fyra lutande skivor i grå-blå plåt, ett platt tak överst och 46 takkupor med fönster. Huset har vita balkonger på våning två och tre, en vit uteplatsbröstning längs bottenvåningen och en hög grå sockel (motorn: ny `golvLyft`). Taket i motorn är `platt` under mansarden.
  - H370 är en liten bod i ljus stående panel med platt tak och mörk takkant. Den turkosa muren mellan trottoaren och parkeringen (cirka 14 m västerut från parkeringens infart) ligger i H370:s fasadlådor, tillsammans med ett gult betongblock vid infarten.
  - H347, huset till höger på fotot från Torggatan 21, ser ut att också ha mansardtak. Det är inte ändrat, eftersom användaren inte har bett om det.
- **Utkast 55: bommarna på Torggatan och Platåvägen är borta.** Nya rutter i `RUTTER` öppnar dem i EPA-läget: "Torggatan väster" från Thulegatan till Nygatan/Platåvägen, och Platåvägen (OSM-vägarna 41644461, 1062800387 och 1062800389). Sidogator som korsar dem, bland annat Landshammarsgatan, Ringvägen och Nivågången, har fortfarande sina bommar. `verktyg/test/bom_test.js` kör en bit på båda gatorna.
- **Utkast 54: Torggatan 17–25** (foto från Torggatan 17). `_torghus` bygger fem likadana trevåningshus på södra sidan väster om Thulegatan: H310 (17), H335 (19), H380 (21), H481 (23) och H599 (25). Bara nummer 17 kommer från fotot; de andra numren är antagna.
  - Husen har ljust beige tegel utan målade fönster (`tegel: 'beige'`), låglutande mörkt tak med ljus takfot och ett ljust betongband över bottenvåningen. Mot gatan har bottenvåningen ett mörkbrunt panelband med fönster.
  - Varje hus har fyra uppgångar A–D (A längst till vänster sett från gatan) med smala lodräta trapphusfönster, entrédörr, trappa med räcken, hortensior och orange skyltar med nummer och bokstav.
  - Motorn: små textskyltar under 2 m ritas i 512 px och delar textur (`smaSkyltTex`).
- **Utkast 53: backen mellan Torggatan och Ringvägen** (foto från Torggatan 23).
  - H337 på krönet är en faluröd villa i en och en halv våning med gråbrunt tak och vita knutar. Mot Torggatan har den en brant tvärgavel (motorns nya form `gavel`) med vita vindskivor, spira och tredelat gavelfönster. Den har också en takkupa, en vit inglasad veranda och en svart skorsten. Marken är planad med höjdankare. En flaggstång står väster om huset, en låg stödmur går längs gångvägen nedanför (G355) och en bänk står vid gångvägen längs Torggatan.
  - H277 är ett sutteränghus i orangebrunt tegel (`tegel: 'brun'`) med fyra rader balkonger med mörkbruna träfronter. `sutterang: true` lägger golvet efter lägsta marken, och höjdankare höjer backen bakom huset.
  - Ny detalj `tradfritt` håller den öppna gräsbacken fri från träd.
- **Utkast 50–52: Circle K och rondellen.** Sök på `utkast 50` och `utkast 52`.
  - Rondellen vid Östra Storgatan/Dansutvägen/Nibblegatan (`RONDELL_C`, `RONDELL_R` = 12,5 m till mittlinjen) är ungefär dubbelt så stor som förut. Ringen G337 är en sluten cirkel och tillfarterna kapas eller förlängs till ringen. Rondellön är grus med en ljus kant.
  - Rondellkonsten är en egen design, en jätteplockepinn med 22 pinnar på 5–7 m i blandade färger (seed 52). Den ersatte "Röset" från utkast 51. Se avsnitt 9.
  - Circle K:
    - H046 är butiken: ljusgrå plåt, glasfasad och röd rand.
    - Taket över pumparna är husdelen H1723 med typen `bensintak`. Det har röd fris med texten CIRCLE K, två pumpöar och lysrör.
    - H1318 är tolkad som biltvätten med släpkärror bredvid; det är inte bekräftat.
    - Pylonen med priser (`prisskyltar`) och orange gatupratare (`reklamskyltar` med `typ: 'tavla'`). Lokalt system `P46_W/R/P`.
- **Utkast 49: Platåvägen efter två foton till.**
  - H736 har gavlar i rött tegel (`tegelSidorRen`) ner till en grå sockel med källarfönster.
  - H737 är lekstugan, i grå-blå panel.
  - 30-skylten är av typen `hastighet`.
  - Häckar, vitt staket och en stödmur längs Platåvägen.
  - H823 är "Villa Villekulla" (gul panel, brant ockragult plåttak, spira, burspråk, svart stålbalkong; husdelarna H1721 och H1722).
  - H867 är ett ljust trähus med 1 m takutsprång (`gavelUtsprang`) och två vita balkonger.
- **Utkast 48: namn, Hitta och Platåvägens början.**
  - Granbackavägen 108 heter **Samuels hus** (H1605, `alias: ["Samuel"]`). Kadriljvägen 1 heter **Mormor** (H1234 och delarna H1712–H1714, `alias: ["Mormors hus"]`).
  - Hus får `adress` från OSM (48 hus) och visar raden "Adress" i husfakta. `platser` innehåller 33 sökbara OSM-noder.
  - **Hitta** (knapp i HUD:en, tangent F):
    - sökruta med träfflista;
    - Dijkstra på bilvägnätet;
    - blå rutt på minikartan, som räknas om varje halvsekund;
    - målskylt med namn, sträcka och ✕, och "Framme vid …!" under 14 m kvar.
    - I EPA-läget används bara den öppna sträckan om målet går att nå därifrån. Annars visas texten "Avstängt i EPA-läget – tryck U för snabbläge".
  - Husen vid Platåvägens början (H736 med flygeln H1720, H751, H789, H823) är rättade efter foto från Nygatan 28.
- **Utkast 47:** hälften så många bilar på STOPP:s kundparkering (37 st), 50 % större hastighetsvisare, avgasrök (`buildRok`) och testet `rok_test.js`.
- **Utkast 46: STOPP Köpcentrum** (H044 med delarna H1715–H1719) efter foto från Östra Storgatan.
  - Lokalt system `ST_W/R/P`, och klassen `Lador` infördes.
  - 71 fasta bilar i rader.
  - Hastighetsvisaren vid x=522, z=198 (`fartskyltar`) visar en glad smiley till och med 40 km/h och en arg över.
  - Motorn fick `panel: 'ligg'`.
- **Utkast 45, påskägg Kadriljvägen 1** (H1234 med delarna H1712–H1714): ett 1½-plans gult tegelhus med en full gård (garage, släpvagn, båt, flaggstång, en grå Peugeot "KDR 001"). Lokalt system `KD_W/R/P` med hjälparna `kbox`, `kskiva`, `krör`, `kpinne`, `kklot` och `kfonster`. Menuettvägen och tomten är planade.
- **Utkast 44:** nya vattentornet (H1711) vid Platåvägen (−1078, 259), förhöjt med `SV = 1.45`. Radio Frösjön spelar `mera_bas.mp3` (Suno-låt av samuelwalfridsson26).
- **Utkast 40–43, påskägg Granbackavägen 108** (H1605, Samuels hus): radhuslängan (`radlanga()`), grannen H1580, cykelställ, sandlåda, studsmatta, parkeringsfickor med en grå Škoda Octavia "GNS 108", garagelängor, en grusväg till H1593 och en vändplan.
- **Utkast 36–39:** buskar vid gångvägen (−63, −3), gamla vattentornet (H032), Margretedalsvägen 15 (H385), Coops lastkaj, Gnesta Hem (H194, Thulegatan 3).
- **Utkast 34–35:** iPhone-kraschen åtgärdad (InstancedMesh för bilar, texturtak), 150 parkerade bilar, helskärm i liggande läge.
- **Tidigare:** stationshuset H006 med Pressbyrån, H008, H010, H068 med fickparkering, Bistro Barens uteservering, snedparkeringar, Torggatan 16, Harsprånget (130 steg), ikoner, delningsbild, ratt och pedaler.

## 12. Öppet och möjliga nästa steg

Användaren har inte svarat på de här frågorna. Ta upp dem bara om det passar, högst en åt gången:

- Ska H347 (till höger på fotot från Torggatan 21) få samma mansardtak som H269?
- Har fler hus i backen samma sutterängstil som H277?
- Stämmer husnumren 19–25 på Torggatan (H335, H380, H481, H599)?
- Är H1318 verkligen biltvätten vid Circle K?
- Thuleparken: var står lekredskapen och P-skylten egentligen? Ett foto av lekplatsen skulle hjälpa.

Kända småsaker som inte är åtgärdade:

- H823 och H736 visar vägg ner till lägsta marken på nedförssidan (ser ut som en extra fönsterrad eller en hög sockel).
- Grannhusen runt Kadriljvägen är generiska tre våningar med platta tak; på fotona är det enplansvillor.
- Vattentornets höjd och proportioner är uppskattade.
- Att GitHub Pages har byggt om är inte verifierat härifrån, eftersom Pages-API:t är blockerat i miljön.

## 13. Fallgropar

- **Webbservern på 8772 dör** när containern startas om, och ibland mellan turer. Kör `forbered.sh` igen, eller `(cd /home/claude/epa-gnesta && setsid python3 -m http.server 8772 >/dev/null 2>&1 &)`. Kontrollera med `curl -s -o /dev/null -w "%{http_code}" http://localhost:8772/index.html` (ska ge 200).
- **Kör generatorn med `python3 -I`** och med båda argumenten (`verktyg/data/gnesta.osm karta.js`). Utan argument kraschar den med IndexError.
- `cd` följer inte alltid med mellan kommandon. Använd absoluta sökvägar.
- Använd `deviceScaleFactor: 1` vid emulering, annars tar skärmbilderna lång tid.
- **Husgolvet** läggs på högsta marken i fotavtrycket (högst 4 m över lägsta). Platta till med höjdankare, använd `sutterang` eller använd `golvLyft` med ett mörkt `band`.
- Hus som är specialbyggda (`SPECIAL_ONLY`) får inga vanliga väggar. Kollisionen mot bilen går via `rekt` om det finns, annars via `poly`.
- **Nya detaljtyper:**
  - De syns bara om motorn har en loop för dem (`DT.namn`).
  - De håller undan träd bara om de är tillagda i `buildTrees()`.
  - Transparenta nät (`depthWrite: false`) försvinner på håll när mipmappen blir för gles. Välj ett grovare mönster (staketnätet har 0,3 m upprepning).
- **Minne:** många små `canvasTex` blir snabbt många megapixel. Använd `smaSkyltTex` och cache, och lådor i stället för klot när det går (`klot` har 16 × 12 segment).
- Plats-, väg- och husnamn i spelet kommer från OSM. Etiketten med vägnamn längst ner i bild gäller bilens position, inte kamerans, så den kan visa en annan gata i renderingar.
