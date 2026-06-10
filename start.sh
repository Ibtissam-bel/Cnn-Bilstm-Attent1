#!/bin/bash
# ── SER Platform — démarrage ──────────────────────────────────────────────────

echo "🎤 SER Platform — Démarrage..."
echo ""

# Vérifier les dépendances
pip install pyjwt pydantic[email] --break-system-packages -q 2>/dev/null || true

# Lancer l'API Auth sur le port 8001 (en arrière-plan)
echo "🔐 Démarrage Auth API (port 8001)..."
cd "$(dirname "$0")"
python3 -m uvicorn auth_api:app --host 0.0.0.0 --port 8001 --reload &
AUTH_PID=$!

# Lancer l'API SER sur le port 8000 (en arrière-plan)  
echo "🎧 Démarrage SER API (port 8000)..."
cd ~/Desktop/ser_api
python3 -m uvicorn main_FastAPI:app --host 0.0.0.0 --port 8000 --reload &
SER_PID=$!

sleep 2
echo ""
echo "✅ APIs démarrées:"
echo "   SER API  → http://localhost:8000"
echo "   Auth API → http://localhost:8001"
echo ""
echo "🌐 Ouvrez dans votre navigateur:"
echo "   file://$(dirname $(realpath "$0"))/index.html"
echo ""
echo "Appuyez sur Ctrl+C pour arrêter"

# Ouvrir automatiquement dans le navigateur
sleep 1
xdg-open "$(dirname $(realpath "$0"))/index.html" 2>/dev/null || true

# Attendre
wait $AUTH_PID $SER_PID
