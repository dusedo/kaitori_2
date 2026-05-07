// Parse Joshin product page HTML and return availability state.
// Primary signal: schema.org JSON-LD <script type="application/ld+json">.
// Fallback: visible Japanese stock phrases.

const JSON_LD_RE = /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;

const TEXT_PATTERNS = [
  { re: /在庫あり/, status: 'InStock' },
  { re: /カートに入れる/, status: 'InStock' },
  { re: /(在庫なし|在庫切れ|完売|販売(?:を)?終了)/, status: 'OutOfStock' },
  { re: /(お取り寄せ|入荷待ち|入荷次第)/, status: 'BackOrder' },
];

function* iterJsonLd(html) {
  for (const m of html.matchAll(JSON_LD_RE)) {
    const raw = m[1].trim();
    try {
      yield JSON.parse(raw);
    } catch {
      // some sites embed multiple objects; try line-by-line as a last resort
    }
  }
}

function flatten(node, out = []) {
  if (!node) return out;
  if (Array.isArray(node)) {
    for (const n of node) flatten(n, out);
  } else if (typeof node === 'object') {
    out.push(node);
    if (node['@graph']) flatten(node['@graph'], out);
  }
  return out;
}

function classifyAvailability(value) {
  if (!value || typeof value !== 'string') return null;
  const v = value.toLowerCase();
  if (v.includes('instock')) return 'InStock';
  if (v.includes('outofstock') || v.includes('soldout')) return 'OutOfStock';
  if (v.includes('preorder') || v.includes('backorder')) return 'BackOrder';
  if (v.includes('discontinued')) return 'Discontinued';
  return null;
}

export function parseAvailability(html) {
  for (const root of iterJsonLd(html)) {
    for (const node of flatten(root)) {
      const types = [].concat(node['@type'] ?? []);
      const isProduct = types.some((t) => /Product|Offer/i.test(String(t)));
      if (!isProduct) continue;
      const offers = [].concat(node.offers ?? []);
      for (const offer of offers) {
        if (!offer || typeof offer !== 'object') continue;
        const status = classifyAvailability(offer.availability);
        if (status) {
          return { status, source: 'json-ld', raw: offer.availability };
        }
      }
      const status = classifyAvailability(node.availability);
      if (status) return { status, source: 'json-ld', raw: node.availability };
    }
  }

  for (const { re, status } of TEXT_PATTERNS) {
    const m = html.match(re);
    if (m) return { status, source: 'text', raw: m[0] };
  }

  return { status: 'Unknown', source: 'none', raw: null };
}

export function extractTitle(html) {
  const m = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return m ? m[1].trim().replace(/\s+/g, ' ').slice(0, 200) : '';
}
