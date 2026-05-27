# Prospect Scraper — Backend

API FastAPI qui expose le scraper d'annuaires partenaires IT.

## Endpoints

- `GET /` → infos service
- `GET /health` → healthcheck
- `GET /sites` → liste des annuaires disponibles
- `POST /scrape?site=citrix&country=FR` → lance le scraping, retourne les partenaires en JSON

## Déploiement Render

1. Repo GitHub : `sore87/prospect-scraper-backend`
2. Render → New → Web Service → connecter le repo
3. **Runtime : Docker** (essentiel pour Playwright)
4. Plan : Starter (gratuit OK pour tester, mais Playwright est gourmand — Starter Plus recommandé en prod)
5. Variable d'env optionnelle : `ALLOWED_ORIGINS=https://prospect-scraper-frontend.vercel.app`
6. Deploy

## Local

```bash
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload
```

API disponible sur http://localhost:8000

## Test rapide

```bash
curl -X POST "http://localhost:8000/scrape?site=citrix&country=FR"
```
