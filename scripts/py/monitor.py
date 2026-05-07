"""Joshin inventory monitor — Python / curl_cffi variant.

Run:
    python -m venv .venv && source .venv/bin/activate
    pip install -r scripts/py/requirements.txt
    cp .env.example .env.local && edit
    python scripts/py/monitor.py

curl_cffi impersonates a real Chrome's TLS fingerprint, which is what kills
naive `requests`/`httpx` calls against behavioural-scoring WAFs. Stick a
session, share cookies across requests, and stay under the rate limit.

Phase 1: monitoring + Discord/LINE notification only. No cart-in.
"""
from __future__ import annotations

import json
import os
import random
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any

from curl_cffi import requests as cf_requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")

STATE_PATH = ROOT / "data" / "state-py.json"
TOP_URL = "https://joshinweb.jp/top.html"

POLL_SEC = int(os.environ.get("POLL_INTERVAL_SEC", "90"))
WATCH_URLS = [u.strip() for u in os.environ.get("WATCH_URLS", "").split(",") if u.strip()]
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_TARGET_ID = os.environ.get("LINE_TARGET_ID", "")

REVIVAL_FROM = {"OutOfStock", "BackOrder", "Unknown", "Discontinued", None}

JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
    re.IGNORECASE,
)
TITLE_RE = re.compile(r"<title[^>]*>([\s\S]*?)</title>", re.IGNORECASE)

TEXT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"在庫あり"), "InStock"),
    (re.compile(r"カートに入れる"), "InStock"),
    (re.compile(r"在庫なし|在庫切れ|完売|販売(?:を)?終了"), "OutOfStock"),
    (re.compile(r"お取り寄せ|入荷待ち|入荷次第"), "BackOrder"),
]


def classify(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.lower()
    if "instock" in v:
        return "InStock"
    if "outofstock" in v or "soldout" in v:
        return "OutOfStock"
    if "preorder" in v or "backorder" in v:
        return "BackOrder"
    if "discontinued" in v:
        return "Discontinued"
    return None


def flatten(node: Any, out: list[dict] | None = None) -> list[dict]:
    if out is None:
        out = []
    if node is None:
        return out
    if isinstance(node, list):
        for n in node:
            flatten(n, out)
    elif isinstance(node, dict):
        out.append(node)
        if "@graph" in node:
            flatten(node["@graph"], out)
    return out


def parse_availability(html: str) -> tuple[str, str, Any]:
    for raw in JSON_LD_RE.findall(html):
        try:
            root = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in flatten(root):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if not any(re.search(r"Product|Offer", str(t), re.I) for t in types):
                continue
            offers = node.get("offers", [])
            if isinstance(offers, dict):
                offers = [offers]
            for offer in offers:
                status = classify(offer.get("availability") if isinstance(offer, dict) else None)
                if status:
                    return status, "json-ld", offer.get("availability")
            status = classify(node.get("availability"))
            if status:
                return status, "json-ld", node.get("availability")

    for regex, status in TEXT_PATTERNS:
        m = regex.search(html)
        if m:
            return status, "text", m.group(0)

    return "Unknown", "none", None


def extract_title(html: str) -> str:
    m = TITLE_RE.search(html)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:200] if m else ""


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text("utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def notify_discord(payload: dict) -> None:
    if not DISCORD_WEBHOOK_URL:
        return
    body = {
        "content": f"🔔 **在庫復活** {payload['prevStatus']} → **{payload['nextStatus']}**",
        "embeds": [
            {
                "title": payload.get("title") or payload["url"],
                "url": payload["url"],
                "description": f"signal: `{payload.get('raw') or 'n/a'}`",
                "color": 0x2ECC71,
            }
        ],
    }
    r = cf_requests.post(DISCORD_WEBHOOK_URL, json=body, timeout=15)
    if r.status_code >= 300:
        raise RuntimeError(f"discord {r.status_code}: {r.text[:200]}")


def notify_line(payload: dict) -> None:
    if not (LINE_TOKEN and LINE_TARGET_ID):
        return
    text = (
        f"🔔 在庫復活: {payload['prevStatus']} → {payload['nextStatus']}\n"
        f"{payload.get('title') or payload['url']}\n{payload['url']}"
    )
    r = cf_requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"authorization": f"Bearer {LINE_TOKEN}"},
        json={"to": LINE_TARGET_ID, "messages": [{"type": "text", "text": text}]},
        timeout=15,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"line {r.status_code}: {r.text[:200]}")


def jitter_sleep(seconds: float) -> None:
    jitter = seconds * 0.25
    time.sleep(max(1.0, seconds + random.uniform(-jitter, jitter)))


def make_session() -> cf_requests.Session:
    s = cf_requests.Session(impersonate="chrome124")
    s.headers.update({
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "ja,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "upgrade-insecure-requests": "1",
    })
    return s


def check_once(session: cf_requests.Session, url: str, state: dict) -> dict:
    try:
        r = session.get(url, headers={"referer": "https://joshinweb.jp/"}, timeout=30)
    except Exception as e:
        print(f"  fetch error: {e}")
        return state

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if r.status_code != 200:
        print(f"[{ts}] {url} HTTP {r.status_code}")
        return state

    avail, source, raw = parse_availability(r.text)
    title = extract_title(r.text)
    prev = state.get(url, {}).get("status")
    print(f"[{ts}] {avail:<13} ({source}) {url}")

    if avail == "InStock" and prev in REVIVAL_FROM:
        print(f"  ↳ revival detected: {prev or '(first)'} → InStock — notifying")
        payload = {
            "title": title,
            "url": url,
            "prevStatus": prev or "unknown",
            "nextStatus": avail,
            "raw": raw,
        }
        try:
            notify_discord(payload)
        except Exception as e:
            print(f"  discord notify failed: {e}")
        try:
            notify_line(payload)
        except Exception as e:
            print(f"  line notify failed: {e}")

    state[url] = {"status": avail, "source": source, "raw": raw, "title": title, "ts": ts}
    return state


def main() -> int:
    if not WATCH_URLS:
        print("WATCH_URLS is empty. Edit .env.local.", file=sys.stderr)
        return 1
    print(f"watching {len(WATCH_URLS)} URL(s) every ~{POLL_SEC}s")

    session = make_session()
    try:
        seed = session.get(TOP_URL, timeout=30)
        print(f"seed {TOP_URL} → {seed.status_code}")
    except Exception as e:
        print(f"seed failed: {e}")

    state = load_state()
    stop = False

    def _on_signal(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    per_url = max(5.0, POLL_SEC / max(1, len(WATCH_URLS)))
    while not stop:
        for url in WATCH_URLS:
            if stop:
                break
            try:
                state = check_once(session, url, state)
                save_state(state)
            except Exception as e:
                print(f"error for {url}: {e}")
            jitter_sleep(per_url)
    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
