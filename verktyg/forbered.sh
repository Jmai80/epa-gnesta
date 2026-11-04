#!/bin/bash
# Förbereder en ny session för EPA-Gnesta. Kör från var som helst: bash verktyg/forbered.sh
# - installerar Python-paketen som generatorn behöver (om de saknas)
# - kopierar testskripten till /home/claude/epa/test
# - startar en webbserver för repots rot på port 8772 (dör ofta mellan turer: kör om skriptet eller sista raden)
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
python3 -c "import numpy, matplotlib" 2>/dev/null || pip install -q --break-system-packages numpy matplotlib
python3 -c "import shapely" 2>/dev/null || pip install -q --break-system-packages shapely || echo "shapely saknas (generatorn klarar sig utan, men en del klippning blir sämre)"
mkdir -p /home/claude/epa/test /tmp/epa-bilder
cp "$REPO"/verktyg/test/*.js /home/claude/epa/test/
pgrep -f "http.serve[r] 8772" >/dev/null || (cd "$REPO" && nohup python3 -m http.server 8772 >/dev/null 2>&1 &)
sleep 1
echo "Repo: $REPO"
echo "Generera kartan:  cd $REPO && python3 -I verktyg/bygg_osm.py verktyg/data/gnesta.osm karta.js"
echo "Felkoll:          node /home/claude/epa/test/fel.js 8772"
