#!/usr/bin/env python3
"""반도체/기판 대시보드 데이터 수집기.

companies.json 의 각 회사에 대해
  - Google News RSS 검색으로 최근 뉴스 (국내: 한국어 hl=ko&gl=KR, 해외: 영어 hl=en-US&gl=US)
  - Yahoo Finance chart 엔드포인트로 시세 (현재가, 등락률, 약 3개월 일봉 종가)
를 가져와 data/data.json 으로 저장한다.

한 회사가 실패해도 전체 실행은 계속되며, 실패한 항목은 직전 data.json 값을 재사용(stale 표시)한다.
의존성: requests (그 외 표준 라이브러리)
"""
from __future__ import annotations

import json
import random
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
COMPANIES = ROOT / "companies.json"
TOPICS = ROOT / "topics.json"
OUT = ROOT / "data" / "data.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})

NEWS_PER_COMPANY = 10
NEWS_WINDOW = "30d"
WORKERS = 4


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url, params=None, tries=3, timeout=20):
    last = None
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1) + random.random())
    raise last


# ---------------------------------------------------------------- news
EXCLUDE: list[str] = []
EXCLUDE_SOURCES: set[str] = set()


def title_key(title: str) -> str:
    return "".join(ch for ch in title.lower() if ch.isalnum())[:80]


def rss_search(q: str, lang: str, window: str = NEWS_WINDOW) -> list[dict]:
    """Google 뉴스 RSS 검색. lang: 'ko' (hl=ko&gl=KR) 또는 'en' (hl=en-US&gl=US)."""
    params = {"q": f"{q} when:{window}"}
    params.update({"hl": "ko", "gl": "KR", "ceid": "KR:ko"} if lang == "ko" else
                  {"hl": "en-US", "gl": "US", "ceid": "US:en"})
    r = get("https://news.google.com/rss/search", params=params)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)].strip()
        if not title or source.lower() in EXCLUDE_SOURCES or any(x in title.lower() for x in EXCLUDE):
            continue
        pub = it.findtext("pubDate")
        try:
            published = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat() if pub else None
        except Exception:  # noqa: BLE001
            published = None
        items.append({"title": title, "source": source,
                      "link": (it.findtext("link") or "").strip(),
                      "published": published, "lang": lang})
    return items


def dedupe_sort(items: list[dict], limit: int) -> list[dict]:
    seen, out = set(), []
    for n in sorted(items, key=lambda x: x["published"] or "", reverse=True):
        k = title_key(n["title"])
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out[:limit]


def fetch_news(company: dict) -> list[dict]:
    kr = company.get("region") == "KR"
    q = company.get("news_query") or (company["name"] if kr else company.get("name_en", company["name"]))
    return dedupe_sort(rss_search(q, "ko" if kr else "en"), NEWS_PER_COMPANY)


def fetch_topic(topic: dict, window: str, limit: int) -> dict:
    items, errors = [], []
    for qd in topic.get("queries", []):
        try:
            items += rss_search(qd["q"], qd.get("lang", "ko"), window)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{qd.get('lang')}: {e}")
    # 한국어/영어가 한쪽에 몰리지 않도록 언어별 상한을 두고 합친다
    per_lang = {}
    for lang in {i["lang"] for i in items}:
        per_lang[lang] = dedupe_sort([i for i in items if i["lang"] == lang], limit)
    merged = dedupe_sort([i for v in per_lang.values() for i in v], limit * 2)
    out = {k: topic[k] for k in ("id", "name") if k in topic}
    out.update({"news": merged, "errors": errors})
    log(f"[topic {topic['id']:<10}] news={len(merged):>2} " + ("OK" if not errors else "WARN " + "; ".join(errors)))
    return out


# ---------------------------------------------------------------- stock
def fetch_quote(ticker: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
    r = get(url, params={"range": "3mo", "interval": "1d", "includePrePost": "false"})
    j = r.json().get("chart", {})
    res = j.get("result")
    if not res:
        raise ValueError(f"{ticker}: {j.get('error')}")
    res = res[0]
    meta = res.get("meta", {})
    ts = res.get("timestamp") or []
    closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    series = [(t, c) for t, c in zip(ts, closes) if c is not None]
    if not series:
        raise ValueError(f"{ticker}: no closes")
    price = meta.get("regularMarketPrice") or series[-1][1]
    off = meta.get("gmtoffset") or 0
    day = lambda t: datetime.fromtimestamp(t + off, timezone.utc).date()  # noqa: E731
    mtime = meta.get("regularMarketTime") or series[-1][0]
    # 마지막 일봉이 오늘(현재가와 같은 거래일)이면 그 전날 종가가 전일 종가
    if len(series) >= 2 and day(series[-1][0]) == day(mtime):
        prev = series[-2][1]
    else:
        prev = series[-1][1]
    change = price - prev if prev else None
    pct = (change / prev * 100) if prev else None
    first = series[0][1]
    return {
        "ticker": ticker,
        "name": meta.get("shortName") or meta.get("longName"),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
        "currency": meta.get("currency"),
        "price": round(price, 4),
        "prev_close": round(prev, 4) if prev else None,
        "change": round(change, 4) if change is not None else None,
        "change_pct": round(pct, 3) if pct is not None else None,
        "change_3m_pct": round((price - first) / first * 100, 2) if first else None,
        "high_3m": round(max(c for _, c in series), 4),
        "low_3m": round(min(c for _, c in series), 4),
        "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
        "market_time": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
        "closes": [[datetime.fromtimestamp(t + off, timezone.utc).strftime("%Y-%m-%d"), round(c, 4)]
                   for t, c in series],
    }


# ---------------------------------------------------------------- main
def process(company: dict, prev: dict) -> dict:
    out = {k: v for k, v in company.items()}
    out["errors"] = []
    old = prev.get(company["id"], {})

    try:
        out["news"] = fetch_news(company)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"news: {e}")
        out["news"] = old.get("news", [])
        out["news_stale"] = True

    if company.get("ticker"):
        try:
            out["quote"] = fetch_quote(company["ticker"])
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"quote: {e}")
            out["quote"] = old.get("quote")
            out["quote_stale"] = True
    else:
        out["quote"] = None

    alts = []
    for t in company.get("alt_tickers", []):
        try:
            q = fetch_quote(t)
            q.pop("closes", None)
            alts.append(q)
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"alt {t}: {e}")
    out["alt_quotes"] = alts

    status = "OK" if not out["errors"] else "WARN " + "; ".join(out["errors"])
    log(f"[{company['id']:<11}] news={len(out['news']):>2} "
        f"price={out['quote'] and out['quote'].get('price')} {status}")
    return out


def main() -> int:
    cfg = json.loads(COMPANIES.read_text(encoding="utf-8"))
    EXCLUDE[:] = [x.lower() for x in cfg.get("news_exclude", [])]
    EXCLUDE_SOURCES.update(x.lower() for x in cfg.get("news_exclude_sources", []))
    prev = {}
    if OUT.exists():
        try:
            prev = {c["id"]: c for c in json.loads(OUT.read_text(encoding="utf-8")).get("companies", [])}
        except Exception:  # noqa: BLE001
            prev = {}

    companies = cfg["companies"]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(lambda c: process(c, prev), companies))

    topics_out = []
    if TOPICS.exists():
        tcfg = json.loads(TOPICS.read_text(encoding="utf-8"))
        prev_topics = {}
        if OUT.exists():
            try:
                prev_topics = {t["id"]: t for t in json.loads(OUT.read_text(encoding="utf-8")).get("topics", [])}
            except Exception:  # noqa: BLE001
                pass
        window, limit = tcfg.get("window", "14d"), tcfg.get("per_topic", 20)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            topics_out = list(ex.map(lambda t: fetch_topic(t, window, limit), tcfg.get("topics", [])))
        for t in topics_out:  # 전부 실패한 토픽은 직전 값 재사용
            if not t["news"] and prev_topics.get(t["id"], {}).get("news"):
                t["news"], t["news_stale"] = prev_topics[t["id"]]["news"], True

    ok_quotes = sum(1 for r in results if r.get("quote") and not r.get("quote_stale"))
    ok_news = sum(1 for r in results if r.get("news") and not r.get("news_stale"))
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "segments": cfg["segments"],
        "companies": results,
        "topics": topics_out,
        "stats": {"companies": len(results), "quotes_ok": ok_quotes, "news_ok": ok_news},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    log(f"done: {len(results)} companies, quotes ok {ok_quotes}, news ok {ok_news} -> {OUT}")
    # 전부 실패한 경우에만 실패 코드 (부분 실패는 성공으로 간주)
    return 0 if (ok_quotes or ok_news) else 1


if __name__ == "__main__":
    sys.exit(main())
