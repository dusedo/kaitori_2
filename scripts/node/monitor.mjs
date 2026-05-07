// Joshin inventory monitor — Node.js / Playwright variant.
//
// Run:
//   npm install
//   npx playwright install chromium
//   cp .env.example .env.local && edit
//   node scripts/node/monitor.mjs
//
// What it does:
//   - Launches a persistent Chromium context (cookies survive between polls).
//   - On cold start, hits the Joshin top page once to seed cookies/Referer.
//   - Polls each WATCH_URLS entry on POLL_INTERVAL_SEC (±25% jitter).
//   - Parses JSON-LD availability; falls back to Japanese text patterns.
//   - On OutOfStock/Unknown → InStock transition, fires Discord + LINE notify.
//
// Phase 1: monitoring + notify only. No cart-in.

import 'dotenv/config';
import { chromium } from 'playwright';
import { resolve } from 'node:path';
import { parseAvailability, extractTitle } from './lib/joshin.mjs';
import { notifyDiscord, notifyLine } from './lib/notify.mjs';
import { loadState, saveState } from './lib/state.mjs';

const STATE_PATH = resolve('data/state-node.json');
const PROFILE_DIR = resolve('data/profile-monitor-node');
const TOP_URL = 'https://joshinweb.jp/top.html';

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

const POLL_SEC = Number(process.env.POLL_INTERVAL_SEC || 90);
const WATCH_URLS = (process.env.WATCH_URLS || '')
  .split(',').map((s) => s.trim()).filter(Boolean);

const REVIVAL_FROM = new Set(['OutOfStock', 'BackOrder', 'Unknown', 'Discontinued', undefined, null]);

function jitterMs(seconds) {
  const ms = seconds * 1000;
  const j = ms * 0.25;
  return Math.floor(ms + (Math.random() * 2 - 1) * j);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function fetchHtml(ctx, url, referer) {
  const res = await ctx.request.get(url, {
    headers: {
      'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'accept-language': 'ja,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7',
      'cache-control': 'no-cache',
      'pragma': 'no-cache',
      'upgrade-insecure-requests': '1',
      ...(referer ? { referer } : {}),
    },
    timeout: 30000,
  });
  return { status: res.status(), html: res.status() === 200 ? await res.text() : '' };
}

async function checkOnce(ctx, url, state) {
  const referer = 'https://joshinweb.jp/';
  const { status, html } = await fetchHtml(ctx, url, referer);
  if (status !== 200) {
    console.warn(`[${new Date().toISOString()}] ${url} HTTP ${status}`);
    return state;
  }

  const { status: avail, source, raw } = parseAvailability(html);
  const title = extractTitle(html);
  const prev = state[url]?.status;
  const ts = new Date().toISOString();
  console.log(`[${ts}] ${avail.padEnd(13)} (${source}) ${url}`);

  if (avail === 'InStock' && REVIVAL_FROM.has(prev)) {
    console.log(`  ↳ revival detected: ${prev ?? '(first)'} → InStock — notifying`);
    const payload = { title, url, prevStatus: prev ?? 'unknown', nextStatus: avail, raw };
    try {
      await notifyDiscord(process.env.DISCORD_WEBHOOK_URL, payload);
    } catch (e) {
      console.error('  discord notify failed:', e.message);
    }
    try {
      await notifyLine(process.env.LINE_CHANNEL_ACCESS_TOKEN, process.env.LINE_TARGET_ID, payload);
    } catch (e) {
      console.error('  line notify failed:', e.message);
    }
  }

  state[url] = { status: avail, source, raw, title, ts };
  return state;
}

async function main() {
  if (WATCH_URLS.length === 0) {
    console.error('WATCH_URLS is empty. Edit .env.local.');
    process.exit(1);
  }
  console.log(`watching ${WATCH_URLS.length} URL(s) every ~${POLL_SEC}s`);

  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    headless: true,
    locale: 'ja-JP',
    timezoneId: 'Asia/Tokyo',
    userAgent: UA,
    viewport: { width: 1280, height: 800 },
    extraHTTPHeaders: { 'accept-language': 'ja,ja-JP;q=0.9,en;q=0.8' },
  });

  // Cold-start: seed cookies via the top page once per process.
  try {
    const seed = await ctx.request.get(TOP_URL, { timeout: 30000 });
    console.log(`seed ${TOP_URL} → ${seed.status()}`);
  } catch (e) {
    console.warn('seed failed:', e.message);
  }

  let state = await loadState(STATE_PATH);

  const shutdown = async (code = 0) => {
    try { await saveState(STATE_PATH, state); } catch {}
    try { await ctx.close(); } catch {}
    process.exit(code);
  };
  process.on('SIGINT', () => shutdown(0));
  process.on('SIGTERM', () => shutdown(0));

  while (true) {
    for (const url of WATCH_URLS) {
      try {
        state = await checkOnce(ctx, url, state);
        await saveState(STATE_PATH, state);
      } catch (e) {
        console.error(`error for ${url}:`, e.message);
      }
      await sleep(jitterMs(Math.max(5, POLL_SEC / WATCH_URLS.length)));
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
