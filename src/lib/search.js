export function search(players, norm, query, limit = 10) {
  const q = norm(query);
  if (!q) return [];
  const toks = q.split(' ');
  const out = [];
  for (const p of players) {
    let ok = true;
    for (const t of toks) {
      if (!p._w.some((w) => w.startsWith(t))) { ok = false; break; }
    }
    if (!ok) continue;
    const rank = p._n === q ? 0 : p._n.startsWith(q) ? 1 : p._w[p._w.length - 1].startsWith(toks[toks.length - 1]) ? 2 : 3;
    out.push([rank, p]);
  }
  out.sort((a, b) => a[0] - b[0] || b[1].g - a[1].g);
  return out.slice(0, limit).map((x) => x[1]);
}
