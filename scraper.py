# -*- coding: utf-8 -*-
"""
Скрапер госзакупок СЗПТ по Актобе.
Поддержка фильтра по году + расширенный поиск.
"""

import re
import time
import logging
from urllib.parse import quote
from typing import List, Dict, Optional

import requests
import urllib3
from bs4 import BeautifulSoup

from config import (
    REFERENCE_PRICES,
    SEARCH_KEYWORDS,
    KATO_AKTOBE,
    THRESHOLD_PERCENT,
    MAX_LOTS_PER_PRODUCT,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    HEADERS,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


def clean_number(text: str) -> Optional[float]:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,]", "", str(text).replace(" ", "").replace("\xa0", ""))
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def is_interesting_status(status: str) -> bool:
    if not status:
        return False
    s = status.lower()
    if any(m in s for m in ["отменено", "отменен"]):
        return False
    return True


def find_product_match(text: str) -> Optional[str]:
    if not text:
        return None
    text_lower = text.lower()
    for product, keywords in SEARCH_KEYWORDS.items():
        for kw in sorted(keywords, key=len, reverse=True):
            if kw in text_lower:
                return product
    return None


def search_and_parse(product_key: str, threshold: float, year: Optional[int] = None) -> List[Dict]:
    keywords = SEARCH_KEYWORDS.get(product_key, [product_key])
    search_terms = keywords[:2]

    results = []
    seen = set()

    for search_word in search_terms:
        url = (
            f"https://goszakup.gov.kz/ru/search/lots"
            f"?filter%5Bname%5D={quote(search_word)}"
            f"&filter%5Bkato%5D={KATO_AKTOBE}"
            f"&count_record=50"
        )
        if year:
            url += f"&filter%5Byear%5D={year}"

        try:
            resp = requests.get(url, headers=HEADERS, verify=False, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "lxml")
        except Exception as e:
            logger.warning(f"Ошибка поиска '{search_word}': {e}")
            continue

        for tr in soup.find_all("tr"):
            a = tr.select_one('a[href*="/ru/announce/index/"]')
            if not a:
                continue

            href = a.get("href", "")
            full_url = "https://goszakup.gov.kz" + href.split("?")[0] + "?tab=lots"
            if full_url in seen:
                continue
            seen.add(full_url)

            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) < 7:
                continue

            lot_id = cells[0]
            announce_info = cells[1]
            lot_name = cells[2]
            qty = clean_number(cells[3])
            total_sum = clean_number(cells[4])
            method = cells[5]
            status = cells[6]

            if not qty or not total_sum or qty <= 0:
                continue

            price_per_unit = total_sum / qty

            if not is_interesting_status(status):
                continue

            matched = find_product_match(lot_name + " " + announce_info)
            use_product = matched if matched else product_key

            ref = REFERENCE_PRICES.get(use_product)
            if not ref:
                continue

            over_percent = ((price_per_unit - ref) / ref) * 100

            if over_percent < threshold:
                continue

            if price_per_unit > ref * 12:
                continue

            title = (lot_name or announce_info).replace("История", "").strip()

            results.append({
                "product": use_product,
                "ref_price": ref,
                "lot_price": round(price_per_unit, 2),
                "over_percent": round(over_percent, 1),
                "qty": qty,
                "total_sum": total_sum,
                "title": title[:160],
                "customer": announce_info[:200],
                "status": status,
                "method": method,
                "url": full_url,
                "lot_id": lot_id,
            })

        time.sleep(REQUEST_DELAY * 0.7)

        if len(results) >= MAX_LOTS_PER_PRODUCT * 2:
            break

    return results


def run_monitor(
    products: Optional[List[str]] = None,
    threshold: float = None,
    year: Optional[int] = None,
) -> List[Dict]:
    if threshold is None:
        threshold = THRESHOLD_PERCENT

    if products is None:
        products = list(REFERENCE_PRICES.keys())

    all_results = []
    seen_urls = set()

    for product in products:
        logger.info(f"Проверяем: {product} (порог +{threshold}%, год={year or 'все'})")
        found = search_and_parse(product, threshold, year=year)

        for item in found:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            all_results.append(item)
            logger.info(
                f"  → +{item['over_percent']}% | {item['lot_price']} тг "
                f"(эталон {item['ref_price']}) | {item['title'][:55]}"
            )

        time.sleep(REQUEST_DELAY)

    all_results.sort(key=lambda x: x["over_percent"], reverse=True)
    return all_results