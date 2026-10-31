const BASE = (import.meta.env && import.meta.env.BASE_URL) || './';

let crcTable;
export function crc32(str) {
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (let i = 0; i < 256; i++) {
      let c = i;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crcTable[i] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  const bytes = new TextEncoder().encode(str);
  for (const b of bytes) crc = crcTable[(crc ^ b) & 255] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

async function getJSON(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`Failed to load ${path} (${res.status})`);
  return res.json();
}

export async function loadIndex() {
  const [meta, players] = await Promise.all([getJSON('data/meta.json'), getJSON('data/players.json')]);
  const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
  for (const p of players) {
    p._n = norm(p.n);
    p._w = p._n.split(' ');
  }
  return { meta, players, norm };
}

const shardCache = new Map();
export async function loadPlayer(meta, id) {
  const s = String(crc32(id) % meta.nShards).padStart(3, '0');
  if (!shardCache.has(s)) shardCache.set(s, getJSON(`data/shards/${s}.json`));
  const shard = await shardCache.get(s);
  return shard[id];
}
