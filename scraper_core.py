"""
Scraper core — adapté du CLI pour usage backend.
Retourne les données en mémoire au lieu d'écrire un CSV.
"""

import asyncio
import logging
import random
import re
from dataclasses import dataclass, asdict
from typing import Optional

from playwright.async_api import async_playwright, Page

# =====================================================================
# CONFIG DES ANNUAIRES (sélecteurs CSS à ajuster après inspection)
# =====================================================================

CONFIGS = {
    "citrix": {
        "name": "Citrix Partner Locator",
        "url": "https://www.citrix.com/buy/partnerlocator/",
        "selectors": {
            "country_select": "select[name='country'], #country, [data-country]",
            "search_button": "button[type='submit'], .search-button, #searchBtn",
            "result_row": ".partner-result, .partner-card, [data-partner]",
            "name": ".partner-name, h3, .name",
            "address": ".partner-address, .address",
            "city": ".partner-city, .city",
            "phone": ".partner-phone, .phone, a[href^='tel:']",
            "website": ".partner-website a, a.website, a[href^='http']:not([href*='citrix'])",
            "level": ".partner-tier, .partner-level, .badge",
        },
        "wait_after_search": 4000,
        "pagination": {"type": "next_button",
                       "next_selector": ".pagination-next, button.next, a[aria-label='Next']",
                       "max_pages": 20},
    },
    "parallels": {
        "name": "Parallels Partner Locator",
        "url": "https://www.parallels.com/partners/locator/",
        "selectors": {
            "country_select": "select[name='country'], #country-select",
            "search_button": "button.search, [type='submit']",
            "result_row": ".partner-item, .partner, .locator-result",
            "name": ".partner-name, h3, h4",
            "address": ".partner-address, .address",
            "city": ".partner-city, .city",
            "phone": "a[href^='tel:'], .phone",
            "website": "a.partner-link, a[href^='http']:not([href*='parallels'])",
            "level": ".tier, .level, .partner-type",
        },
        "wait_after_search": 4000,
        "pagination": {"type": "scroll", "max_scrolls": 30},
    },
    "omnissa": {
        "name": "Omnissa Partner Locator (ex-VMware EUC)",
        "url": "https://partnerlocator.omnissa.com/",
        "selectors": {
            "country_select": "select[name='country'], #country",
            "search_button": "button[type='submit'], .btn-search",
            "result_row": ".partner-card, .result-item, [data-partner]",
            "name": ".company-name, h3, h4",
            "address": ".address, .partner-address",
            "city": ".city",
            "phone": "a[href^='tel:'], .phone",
            "website": "a[href^='http']:not([href*='omnissa'])",
            "level": ".partner-level, .tier",
        },
        "wait_after_search": 4000,
        "pagination": {"type": "next_button",
                       "next_selector": ".pagination-next, .next, [aria-label='Next page']",
                       "max_pages": 20},
    },
}

COUNTRY_CODES = {
    "FR": ["France", "FR", "fr", "FRA"],
    "BE": ["Belgium", "BE", "Belgique"],
    "CH": ["Switzerland", "Suisse", "CH"],
    "LU": ["Luxembourg", "LU"],
    "DE": ["Germany", "Deutschland", "DE"],
    "ES": ["Spain", "España", "ES"],
    "IT": ["Italy", "Italia", "IT"],
    "UK": ["United Kingdom", "UK", "GB", "Royaume-Uni"],
}


@dataclass
class Partner:
    source: str = ""
    name: str = ""
    level: str = ""
    address: str = ""
    city: str = ""
    postcode: str = ""
    country: str = ""
    phone: str = ""
    website: str = ""
    raw_text: str = ""

    def to_dict(self):
        return asdict(self)


class DirectoryScraper:
    def __init__(self, site_key, country="FR", headless=True, delay_range=(2.0, 4.0)):
        if site_key not in CONFIGS:
            raise ValueError(f"Site inconnu : {site_key}")
        self.site_key = site_key
        self.config = CONFIGS[site_key]
        self.country = country
        self.headless = headless
        self.delay_range = delay_range
        self.partners: list[Partner] = []
        self.log = logging.getLogger(site_key)

    async def _pause(self):
        await asyncio.sleep(random.uniform(*self.delay_range))

    async def _try_select_country(self, page: Page) -> bool:
        sel = self.config["selectors"]["country_select"]
        labels = COUNTRY_CODES.get(self.country, [self.country])
        for selector in sel.split(","):
            selector = selector.strip()
            try:
                el = await page.query_selector(selector)
                if el:
                    tag = await el.evaluate("e => e.tagName.toLowerCase()")
                    if tag == "select":
                        for label in labels:
                            try:
                                await page.select_option(selector, label=label)
                                return True
                            except Exception:
                                try:
                                    await page.select_option(selector, value=label)
                                    return True
                                except Exception:
                                    continue
            except Exception:
                continue
        return False

    async def _click_search(self, page: Page):
        for selector in self.config["selectors"]["search_button"].split(","):
            try:
                el = await page.query_selector(selector.strip())
                if el:
                    await el.click()
                    return
            except Exception:
                continue
        await page.keyboard.press("Enter")

    async def _extract_text(self, element, selectors_str: str) -> str:
        for selector in selectors_str.split(","):
            try:
                sub = await element.query_selector(selector.strip())
                if sub:
                    text = await sub.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        return ""

    async def _extract_attr(self, element, selectors_str: str, attr: str) -> str:
        for selector in selectors_str.split(","):
            try:
                sub = await element.query_selector(selector.strip())
                if sub:
                    val = await sub.get_attribute(attr)
                    if val:
                        return val.strip()
            except Exception:
                continue
        return ""

    async def _parse_results(self, page: Page) -> int:
        sels = self.config["selectors"]
        rows = []
        for selector in sels["result_row"].split(","):
            try:
                found = await page.query_selector_all(selector.strip())
                if found:
                    rows = found
                    break
            except Exception:
                continue
        if not rows:
            # Aucun résultat trouvé — log de debug pour identifier les bons sélecteurs
            self.log.warning(f"❌ Aucun résultat avec sélecteurs {sels['result_row']!r}")
            try:
                body_text = await page.evaluate("document.body.innerText")
                self.log.info(f"body length: {len(body_text)} chars")
                self.log.info(f"body sample: {body_text[:300]!r}")
                # Classes CSS les plus fréquentes sur la page
                top_classes = await page.evaluate("""
                    () => {
                        const counts = {};
                        document.querySelectorAll('[class]').forEach(el => {
                            el.className.toString().split(/\\s+/).forEach(c => {
                                if (c) counts[c] = (counts[c] || 0) + 1;
                            });
                        });
                        return Object.entries(counts)
                            .sort((a,b) => b[1]-a[1])
                            .slice(0, 30)
                            .map(([c,n]) => `${c}(${n})`);
                    }
                """)
                self.log.info(f"top classes: {top_classes}")
            except Exception as e:
                self.log.warning(f"debug introspection failed: {e}")
            return 0

        new_count = 0
        for row in rows:
            p = Partner(source=self.config["name"], country=self.country)
            p.name = await self._extract_text(row, sels["name"])
            p.address = await self._extract_text(row, sels["address"])
            p.city = await self._extract_text(row, sels["city"])
            p.phone = await self._extract_text(row, sels["phone"])
            if not p.phone:
                p.phone = (await self._extract_attr(row, "a[href^='tel:']", "href")).replace("tel:", "")
            p.website = await self._extract_attr(row, sels["website"], "href")
            p.level = await self._extract_text(row, sels["level"])
            m = re.search(r"\b(\d{4,5})\b", p.address + " " + p.city)
            if m:
                p.postcode = m.group(1)
            try:
                p.raw_text = (await row.inner_text())[:500]
            except Exception:
                pass
            if p.name:
                self.partners.append(p)
                new_count += 1
        return new_count

    async def _paginate(self, page: Page):
        pag = self.config["pagination"]
        if pag["type"] == "next_button":
            for _ in range(pag.get("max_pages", 10)):
                clicked = False
                for selector in pag["next_selector"].split(","):
                    try:
                        btn = await page.query_selector(selector.strip())
                        if btn:
                            disabled = await btn.get_attribute("disabled")
                            aria_dis = await btn.get_attribute("aria-disabled")
                            if disabled or aria_dis == "true":
                                return
                            await btn.click()
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    return
                await self._pause()
                await self._parse_results(page)
        elif pag["type"] == "scroll":
            prev = 0
            for _ in range(pag.get("max_scrolls", 20)):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self._pause()
                await self._parse_results(page)
                if len(self.partners) == prev:
                    return
                prev = len(self.partners)

    async def run(self):
        self.log.info(f"Scraping {self.config['name']} pour {self.country}")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                locale="fr-FR",
            )
            page = await context.new_page()
            # `networkidle` ne marche pas sur les sites corporate (trackers/analytics
            # continus). `domcontentloaded` charge le DOM puis on attend que le JS pose
            # ses composants via un wait fixe.
            self.log.info(f"goto {self.config['url']}")
            await page.goto(self.config["url"], wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)  # laisser le JS s'initialiser
            await self._pause()
            self.log.info(f"page loaded, title={await page.title()!r}")

            ok = await self._try_select_country(page)
            if ok:
                await self._pause()
                await self._click_search(page)
                await page.wait_for_timeout(self.config["wait_after_search"])

            await self._parse_results(page)
            await self._paginate(page)
            await browser.close()

        self.log.info(f"Terminé : {len(self.partners)} partenaires extraits")
