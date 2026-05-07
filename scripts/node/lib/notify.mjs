export async function notifyDiscord(webhookUrl, { title, url, prevStatus, nextStatus, raw }) {
  if (!webhookUrl) return { skipped: 'no DISCORD_WEBHOOK_URL' };
  const body = {
    content: `🔔 **在庫復活** ${prevStatus} → **${nextStatus}**`,
    embeds: [
      {
        title: title || url,
        url,
        description: `signal: \`${raw ?? 'n/a'}\``,
        color: 0x2ecc71,
        timestamp: new Date().toISOString(),
      },
    ],
  };
  const res = await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`discord ${res.status}: ${text.slice(0, 200)}`);
  }
  return { ok: true };
}

export async function notifyLine(token, targetId, { title, url, prevStatus, nextStatus }) {
  if (!token || !targetId) return { skipped: 'no LINE creds' };
  const text = `🔔 在庫復活: ${prevStatus} → ${nextStatus}\n${title || url}\n${url}`;
  const res = await fetch('https://api.line.me/v2/bot/message/push', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ to: targetId, messages: [{ type: 'text', text }] }),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => '');
    throw new Error(`line ${res.status}: ${t.slice(0, 200)}`);
  }
  return { ok: true };
}
