// Cell formatting that mirrors Baseball-Reference conventions.
const DEC3 = new Set(['BA', 'OBP', 'SLG', 'OPS', 'W-L%']);
const DEC2 = new Set(['ERA', 'FIP', 'SO/BB']);
const DEC1 = new Set(['H9', 'HR9', 'BB9', 'SO9']);

export function formatCell(col, v) {
  if (v === null || v === undefined || v === '') return '';
  if (typeof v === 'string') return v;
  if (DEC3.has(col)) {
    const s = v.toFixed(3);
    return v < 1 ? s.replace(/^0/, '') : s;
  }
  if (col === 'WHIP') return v.toFixed(3);
  if (DEC2.has(col)) return v.toFixed(2);
  if (DEC1.has(col)) return v.toFixed(1);
  if (col === 'WAR') return v.toFixed(1);
  if (col === 'IP') return `${Math.floor(v / 3)}.${v % 3}`;
  return String(v);
}

export const TOOLTIPS = {
  Age: "Player's age on June 30th of that year",
  Team: 'Team', Lg: 'League', WAR: 'Wins Above Replacement',
  G: 'Games played', PA: 'Plate appearances', AB: 'At bats', R: 'Runs scored / allowed', H: 'Hits',
  '2B': 'Doubles', '3B': 'Triples', HR: 'Home runs', RBI: 'Runs batted in', SB: 'Stolen bases',
  CS: 'Caught stealing', BB: 'Bases on balls (walks)', SO: 'Strikeouts', BA: 'Batting average',
  OBP: 'On-base percentage', SLG: 'Slugging percentage', OPS: 'On-base plus slugging',
  'OPS+': 'Adjusted OPS (100 = league average)', TB: 'Total bases', GIDP: 'Grounded into double plays',
  HBP: 'Hit by pitch', SH: 'Sacrifice hits (bunts)', SF: 'Sacrifice flies', IBB: 'Intentional bases on balls',
  Pos: 'Positions played (1=P 2=C 3=1B 4=2B 5=3B 6=SS 7=LF 8=CF 9=RF D=DH); * = played 2/3+ of team games there',
  W: 'Wins', L: 'Losses', 'W-L%': 'Win-loss percentage', ERA: 'Earned run average', GS: 'Games started',
  GF: 'Games finished', CG: 'Complete games', SHO: 'Shutouts', SV: 'Saves', IP: 'Innings pitched',
  ER: 'Earned runs', BK: 'Balks', WP: 'Wild pitches', BF: 'Batters faced', 'ERA+': 'Adjusted ERA (100 = league average)',
  FIP: 'Fielding independent pitching', WHIP: '(Walks + hits) per inning pitched', H9: 'Hits per 9 innings',
  HR9: 'Home runs per 9 innings', BB9: 'Walks per 9 innings', SO9: 'Strikeouts per 9 innings',
  'SO/BB': 'Strikeout-to-walk ratio',
  Awards: 'AS=All-Star, MVP/CYA/ROY-n = finish in voting, GG=Gold Glove, SS=Silver Slugger',
};

// Column key used by the data pipeline for each displayed column.
// OPS+ and ERA+ are our own approximations (park factors differ slightly from Baseball-Reference).
export const APPROX_COLS = new Set(['OPS+', 'ERA+']);
export function headerLabel(c) { return APPROX_COLS.has(c) ? `${c}*` : c; }

export function yearsLabel(p) { return p.y[0] === p.y[1] ? `${p.y[0]}` : `${p.y[0]}–${p.y[1]}`; }