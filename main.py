"""
Prospect Scraper Backend — FastAPI
Expose /scrape pour lancer le scraping d'un annuaire partenaire.
"""

import logging
import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from scraper_core import DirectoryScraper, CONFIGS

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")

app = FastAPI(
    title="Prospect Scraper API",
    description="API d'extraction de partenaires depuis les annuaires des éditeurs IT",
    version="1.0.0",
)

# CORS — autorise le frontend Vercel
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "prospect-scraper",
        "status": "ok",
        "endpoints": ["/health", "/sites", "/scrape"],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sites")
def list_sites():
    """Liste les annuaires disponibles."""
    return [
        {"key": k, "name": v["name"], "url": v["url"]}
        for k, v in CONFIGS.items()
    ]


@app.post("/scrape")
async def scrape(
    site: str = Query(..., description="Clé du site (citrix, parallels, omnissa)"),
    country: str = Query("FR", description="Code pays ISO"),
):
    """Lance le scraping d'un annuaire et retourne les partenaires en JSON."""
    if site not in CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Site inconnu. Disponibles : {list(CONFIGS.keys())}",
        )

    try:
        scraper = DirectoryScraper(site_key=site, country=country, headless=True)
        await scraper.run()
        return {
            "site": site,
            "site_name": CONFIGS[site]["name"],
            "country": country,
            "count": len(scraper.partners),
            "partners": [p.to_dict() for p in scraper.partners],
        }
    except Exception as e:
        logging.exception("Scrape failed")
        raise HTTPException(status_code=500, detail=str(e))
