#!/bin/bash
cd "$(dirname "$0")"

# Create venv if not exists
if [ ! -d "venv" ]; then
  echo "📦 Erstelle virtuelle Umgebung..."
  python3 -m venv venv
  source venv/bin/activate
  pip install -q -r requirements.txt
else
  source venv/bin/activate
fi

# Copy env if not exists
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "⚠️  .env erstellt – trage deinen ANTHROPIC_API_KEY ein für KI-Fragen (optional)"
fi

echo ""
echo "🟢 P&K Funnel Generator → http://localhost:5050"
echo ""
python app.py
