// Primary team colors (by the abbreviation shown in the Team column), used for a soft highlight on the leading cells.
// Teams not listed simply get no highlight.
const C = {
  ARI: '#A71930', ATL: '#CE1141', BAL: '#DF4601', BOS: '#BD3039', CHC: '#0E3386', CHW: '#6b6b6b',
  CIN: '#C6011F', CLE: '#E31937', COL: '#5b2d9e', DET: '#1d3f73', HOU: '#EB6E1F', KCR: '#004687',
  LAA: '#BA0021', ANA: '#BA0021', CAL: '#BA0021', LAD: '#005A9C', BRO: '#005A9C',
  MIA: '#00A3E0', FLA: '#00A3E0', MIL: '#FFC52F', MIN: '#2a5aa8', NYM: '#FF5910', NYY: '#3b5b8f',
  OAK: '#2d7a5f', ATH: '#2d7a5f', PHA: '#2d7a5f', KCA: '#2d7a5f', PHI: '#E81828', PIT: '#FDB827',
  SDP: '#8a6a4a', SFG: '#FD5A1E', NYG: '#FD5A1E', SEA: '#007a7a', STL: '#C41E3A', SLB: '#E8710A',
  TBR: '#8FBCE6', TBD: '#8FBCE6', TEX: '#2a5aa8', TOR: '#134A8E', WSH: '#AB0003', WSN: '#AB0003',
  WAS: '#AB0003', MON: '#2a5aa8', BSN: '#CE1141', MLN: '#CE1141', WSA: '#9B1B30',
};
export const teamColor = (abbr) => C[abbr] || null;

// Readable text color (black or white) for a given background hex color.
export function textOn(hex) {
  const n = parseInt(hex.slice(1), 16);
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const L = 0.2126 * lin(n >> 16) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
  return L > 0.4 ? '#111' : '#fff';
}