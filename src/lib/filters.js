export const DEFAULT_FILTERS = {
  yearFrom: 2000, yearTo: 2025, type: 'both', minPA: 4000, minIP: 600, minG: 0,
  positions: [], teams: [], teamMode: 'or', notable: true,
};

// Position chips (hitting positions, plus P when pitchers are in the pool).
export const HITTER_POSITIONS = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'DH'];

export const defaultFilters = (meta) => ({ ...DEFAULT_FILTERS, yearTo: meta.lastSeason });

export function loadSavedFilters(meta) {
  try {
    const raw = JSON.parse(localStorage.getItem('rg.filters') || 'null');
    if (raw) return { ...DEFAULT_FILTERS, ...raw };
  } catch { /* storage unavailable */ }
  return { ...DEFAULT_FILTERS, yearTo: meta.lastSeason };
}

export function saveFilters(f) {
  try { localStorage.setItem('rg.filters', JSON.stringify(f)); } catch { /* ignore */ }
}

// "Notable" players have something in their Awards column or led a league in some stat (p.nt, set by the data build).
// Which minimums apply depends on the player type; options that are hidden in the UI are ignored here too.
//   Hitters  -> plate appearances (+ position)
//   Pitchers -> innings pitched and games pitched
//   Both     -> plate appearances, innings pitched, games pitched (+ position, where P means pitcher)
export function eligible(players, f) {
  const teams = f.teams || [];
  const needAll = f.teamMode === 'and';
  const from = Number(f.yearFrom) || 0, to = Number(f.yearTo) || 9999;
  const minPA = Number(f.minPA) || 0, minIP = Number(f.minIP) || 0, minG = Number(f.minG) || 0;
  const pos = new Set((f.positions || []).filter((x) => f.type === 'both' || x !== 'P'));
  return players.filter((p) => {
    if (f.notable && !p.nt) return false;
    if (!p.ys.some((y) => y >= from && y <= to)) return false;
    if (teams.length) {
      const ok = needAll ? teams.every((t) => p.f.includes(t)) : teams.some((t) => p.f.includes(t));
      if (!ok) return false;
    }
    if (f.type === 'bat') {
      if (!p.t.includes('b') || p.pa < minPA) return false;
      return !pos.size || p.ps.some((x) => pos.has(x));
    }
    if (f.type === 'pit') return p.t.includes('p') && p.ip >= minIP && p.gp >= minG;
    const hit = p.t.includes('b') && p.pa >= minPA;
    const pit = p.t.includes('p') && p.ip >= minIP && p.gp >= minG;
    if (!hit && !pit) return false;
    return !pos.size || p.ps.some((x) => pos.has(x));
  });
}