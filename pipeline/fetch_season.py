#!/usr/bin/env python3
"""
Fetch one MLB regular season from the public MLB Stats API and write Lahman-schema CSVs
that build_data.py can append with --extra-dir.   (Used for 2026, before Lahman publishes it.)

Usage:
  python fetch_season.py --lahman /path/to/Lahman --register /path/to/register [--season 2026] [--out ../extra-2026]
  python build_data.py   --lahman /path/to/Lahman --register /path/to/register --extra-dir ../extra-2026

Writes to --out:  Batting.csv  Pitching.csv  Appearances.csv  Teams.csv  People.csv   (+ raw/ cache of API responses)
  - Awards and All-Star selections are NOT fetched (not final yet); build_data.py simply has none for the season.
  - Teams.csv: park factors (BPF/PPF) are carried over from the previous season, so OPS+/ERA+ use last year's parks.
  - Players missing from Lahman's People table get a new row; their playerID is the Baseball-Reference ID from the
    Chadwick register when known, otherwise a generated BR-style ID (lastname5 + first2 + 01).
  - Re-run any time (e.g. to pick up a late correction); responses are cached in --out/raw, use --refresh to refetch.

Only the Python standard library + pandas/numpy are needed.
"""
import argparse, glob, json, os, re, sys, time, unicodedata
import urllib.parse, urllib.request
from collections import defaultdict
import pandas as pd
from rdata import read_rdata

API = 'https://statsapi.mlb.com/api/v1'

# MLB team id -> Baseball-Reference team code (as in Lahman Teams.teamIDBR)
MLB_TEAMS = {108: 'LAA', 109: 'ARI', 110: 'BAL', 111: 'BOS', 112: 'CHC', 113: 'CIN', 114: 'CLE', 115: 'COL',
             116: 'DET', 117: 'HOU', 118: 'KCR', 119: 'LAD', 120: 'WSN', 121: 'NYM', 133: 'ATH', 134: 'PIT',
             135: 'SDP', 136: 'SEA', 137: 'SFG', 138: 'STL', 139: 'TBR', 140: 'TEX', 141: 'TOR', 142: 'MIN',
             143: 'PHI', 144: 'ATL', 145: 'CHW', 146: 'MIA', 147: 'NYY', 158: 'MIL'}

HIT = {'gamesPlayed': 'G', 'atBats': 'AB', 'runs': 'R', 'hits': 'H', 'doubles': 'X2B', 'triples': 'X3B',
       'homeRuns': 'HR', 'rbi': 'RBI', 'stolenBases': 'SB', 'caughtStealing': 'CS', 'baseOnBalls': 'BB',
       'strikeOuts': 'SO', 'intentionalWalks': 'IBB', 'hitByPitch': 'HBP', 'sacBunts': 'SH', 'sacFlies': 'SF',
       'groundIntoDoublePlay': 'GIDP'}
PIT = {'wins': 'W', 'losses': 'L', 'gamesPlayed': 'G', 'gamesStarted': 'GS', 'completeGames': 'CG',
       'shutouts': 'SHO', 'saves': 'SV', 'hits': 'H', 'earnedRuns': 'ER', 'homeRuns': 'HR', 'baseOnBalls': 'BB',
       'strikeOuts': 'SO', 'intentionalWalks': 'IBB', 'wildPitches': 'WP', 'hitByPitch': 'HBP', 'balks': 'BK',
       'battersFaced': 'BFP', 'gamesFinished': 'GF', 'runs': 'R'}
BAT_OUT = ['playerID', 'yearID', 'stint', 'teamID', 'lgID', 'G', 'AB', 'R', 'H', 'X2B', 'X3B', 'HR', 'RBI', 'SB',
           'CS', 'BB', 'SO', 'IBB', 'HBP', 'SH', 'SF', 'GIDP']
PIT_OUT = ['playerID', 'yearID', 'stint', 'teamID', 'lgID', 'W', 'L', 'G', 'GS', 'CG', 'SHO', 'SV', 'IPouts', 'H',
           'ER', 'HR', 'BB', 'SO', 'IBB', 'WP', 'HBP', 'BK', 'BFP', 'GF', 'R']
POS_G = {'C': 'G_c', '1B': 'G_1b', '2B': 'G_2b', '3B': 'G_3b', 'SS': 'G_ss', 'LF': 'G_lf', 'CF': 'G_cf', 'RF': 'G_rf'}


# ------------------------------------------------------------------ API access (cached)
def get(url, cache_file, refresh=False, tries=4):
    if os.path.exists(cache_file) and not refresh:
        with open(cache_file) as f:
            return json.load(f)
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'refguess-data-builder'})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(data, f)
            return data
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                raise SystemExit(f'API request failed: {url}\n  {e}')
            time.sleep(2 * (k + 1))


def stat_pages(raw, season, group, refresh, **extra):
    """All splits of /stats?stats=season for a group (paged)."""
    out, offset, limit = [], 0, 1000
    while True:
        q = dict(stats='season', group=group, season=season, gameType='R', playerPool='All', sportIds=1,
                 limit=limit, offset=offset, **extra)
        tag = '_'.join(f'{k}-{v}' for k, v in sorted(extra.items())) or 'all'
        d = get(f'{API}/stats?' + urllib.parse.urlencode(q), f'{raw}/stats_{group}_{tag}_{offset}.json', refresh)
        splits = (d.get('stats') or [{}])[0].get('splits', [])
        out += splits
        if len(splits) < limit:
            return out
        offset += limit


def fetch_people(ids, season, raw, refresh):
    """Per-player year-by-year stats (per-team rows) + bio, in batches."""
    people = []
    ids = sorted(ids)
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        hyd = f'stats(group=[hitting,pitching,fielding],type=[yearByYear],season={season})'
        q = urllib.parse.urlencode({'personIds': ','.join(map(str, chunk)), 'hydrate': hyd})
        d = get(f'{API}/people?{q}', f'{raw}/people_{i:05d}.json', refresh)
        people += d.get('people', [])
        print(f'\r  players {min(i + 40, len(ids))}/{len(ids)}', end='', flush=True)
    print()
    return people


# ------------------------------------------------------------------ helpers
def num(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def outs(ip):
    """'123.2' innings -> outs."""
    if ip in (None, ''):
        return 0
    w, _, f = str(ip).partition('.')
    return 3 * int(w or 0) + int(f or 0)


def ascii_name(s):
    return re.sub(r'[^a-z]', '', unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower())


def height_in(s):
    m = re.match(r"(\d+)'\s*(\d+)", s or '')
    return int(m.group(1)) * 12 + int(m.group(2)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lahman', required=True)
    ap.add_argument('--register', required=True)
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--out')
    ap.add_argument('--refresh', action='store_true', help='ignore the cache and re-download')
    a = ap.parse_args()
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', f'extra-{a.season}')
    raw = os.path.join(out, 'raw')
    os.makedirs(raw, exist_ok=True)
    S = a.season

    # ---- Lahman reference tables
    rd = lambda n: list(read_rdata(os.path.join(a.lahman, 'data', n + '.RData')).values())[0]  # noqa: E731
    lteams, lpeople = rd('Teams'), rd('People')
    prev = lteams[lteams.yearID == lteams.yearID.max()].drop_duplicates('teamID')
    tm = {}
    for mid, br in MLB_TEAMS.items():
        r = prev[prev.teamIDBR == br]
        if r.empty:
            raise SystemExit(f'No {prev.yearID.iloc[0]} Lahman team with teamIDBR={br} (MLB id {mid}); update MLB_TEAMS.')
        tm[mid] = r.iloc[0]
    print(f'teams ok ({len(tm)})')

    reg = pd.concat([pd.read_csv(f, dtype=str, usecols=['key_mlbam', 'key_bbref', 'key_retro'])
                     for f in glob.glob(os.path.join(a.register, 'data', 'people-*.csv'))])
    reg = reg.dropna(subset=['key_mlbam']).drop_duplicates('key_mlbam').set_index('key_mlbam')
    bb2lah = lpeople.dropna(subset=['bbrefID']).set_index('bbrefID').playerID.to_dict()
    taken = set(lpeople.playerID)
    lah_ids = set(taken)

    # ---- who played: ids from the league-wide stat tables
    print('downloading league stat tables...')
    hit_all = stat_pages(raw, S, 'hitting', a.refresh)
    pit_all = stat_pages(raw, S, 'pitching', a.refresh)
    ids = {s['player']['id'] for s in hit_all + pit_all if s.get('player')}
    print(f'  {len(ids)} players with {S} stats')
    # games as DH / pinch hitter / pinch runner (per player; split across teams below if needed)
    extra_g = {}
    for pos, col in (('DH', 'G_dh'), ('PH', 'G_ph'), ('PR', 'G_pr')):
        for s in stat_pages(raw, S, 'hitting', a.refresh, position=pos):
            if s.get('player'):
                t = (s.get('team') or {}).get('id')
                extra_g.setdefault((s['player']['id'], t, col), 0)
                extra_g[(s['player']['id'], t, col)] += num(s['stat'].get('gamesPlayed'))

    print('downloading player detail...')
    people = fetch_people(ids, S, raw, a.refresh)

    bat, pit, app, newp = [], [], [], []
    for p in people:
        mid = str(p['id'])
        bbk = reg.key_bbref.get(mid) if mid in reg.index else None
        bbk = bbk if isinstance(bbk, str) and bbk else None
        # existing Lahman player: matched by bbrefID, or by playerID (which is normally the same string)
        pid = bb2lah.get(bbk) or (bbk if bbk in lah_ids else None)
        if not pid:   # not in Lahman yet -> new People row
            bbref = reg.key_bbref.get(mid) if mid in reg.index else None
            pid = bbref if isinstance(bbref, str) and bbref else None
            if not pid:
                base = (ascii_name(p.get('lastName'))[:5] + ascii_name(p.get('firstName'))[:2])
                n = 1
                while f'{base}{n:02d}' in taken:
                    n += 1
                pid = f'{base}{n:02d}'
            taken.add(pid)
            bd = ((p.get('birthDate') or '').split('-') + [None] * 3)[:3]
            newp.append({'playerID': pid, 'birthYear': num(bd[0]) or None,
                         'birthMonth': num(bd[1]) or None, 'birthDay': num(bd[2]) or None,
                         'birthCity': p.get('birthCity'), 'birthCountry': p.get('birthCountry'),
                         'birthState': p.get('birthStateProvince'), 'nameFirst': p.get('firstName'),
                         'nameLast': p.get('lastName'), 'nameGiven': p.get('firstName'),
                         'weight': p.get('weight'), 'height': height_in(p.get('height')),
                         'bats': (p.get('batSide') or {}).get('code'), 'throws': (p.get('pitchHand') or {}).get('code'),
                         'debut': p.get('mlbDebutDate'), 'bbrefID': bbref if isinstance(bbref, str) else pid,
                         'finalGame': None, 'retroID': reg.key_retro.get(mid) if mid in reg.index else None,
                         'birthDate': p.get('birthDate')})

        rows = defaultdict(lambda: {'h': None, 'p': None, 'f': defaultdict(int)})   # team id -> data
        order = []
        for grp in p.get('stats', []):
            g = grp.get('group', {}).get('displayName')
            for sp in grp.get('splits', []):
                t = sp.get('team') or {}
                if str(sp.get('season')) != str(S) or t.get('id') not in MLB_TEAMS or (sp.get('sport') or {}).get('id', 1) != 1:
                    continue   # other seasons, minor leagues, or the combined "total" row
                tid = t['id']
                if tid not in order:
                    order.append(tid)
                st = sp['stat']
                if g == 'hitting':
                    rows[tid]['h'] = {v: num(st.get(k)) for k, v in HIT.items()}
                elif g == 'pitching':
                    d = {v: num(st.get(k)) for k, v in PIT.items()}
                    d['IPouts'] = outs(st.get('inningsPitched'))
                    rows[tid]['p'] = d
                elif g == 'fielding':
                    ab = (sp.get('position') or {}).get('abbreviation')
                    rows[tid]['f'][ab] += num(st.get('gamesPlayed'))
        for stint, tid in enumerate(order, 1):
            r, t = rows[tid], tm[tid]
            base = {'playerID': pid, 'yearID': S, 'stint': stint, 'teamID': t.teamID, 'lgID': t.lgID}
            h, pp = r['h'], r['p']
            if h and h['G'] > 0:
                bat.append({**base, **{c: h[c] for c in BAT_OUT[5:]}})
            if pp and pp['G'] > 0:
                pit.append({**base, **{c: pp[c] for c in PIT_OUT[5:]}})
            f = r['f']
            ap_row = {'yearID': S, 'teamID': t.teamID, 'lgID': t.lgID, 'playerID': pid,
                      'G_batting': h['G'] if h else 0, 'G_p': pp['G'] if pp else 0}
            ap_row['GS'] = pp['GS'] if pp else 0
            for ab, col in POS_G.items():
                ap_row[col] = f.get(ab, 0)
            of = f.get('LF', 0) + f.get('CF', 0) + f.get('RF', 0)
            ap_row['G_of'] = max(f.get('OF', 0), of)
            for col in ('G_dh', 'G_ph', 'G_pr'):
                v = extra_g.get((p['id'], tid, col))
                if v is None:   # API gave this player's total only (no team): put it on the team with most games
                    tot = extra_g.get((p['id'], None, col), 0)
                    best = max(order, key=lambda x: (rows[x]['h'] or {}).get('G', 0))
                    v = tot if tid == best else 0
                ap_row[col] = v
            ap_row['G_defense'] = max([f.get(k, 0) for k in list(POS_G) + ['OF']] + [ap_row['G_p'], of])
            ap_row['G_all'] = max(ap_row['G_batting'], ap_row['G_p'], ap_row['G_defense'])
            if ap_row['G_all'] > 0:
                app.append(ap_row)

    # ---- Teams rows for the season (everything Lahman-specific copied from the previous season)
    teams = []
    for mid, t in tm.items():
        teams.append({'yearID': S, 'lgID': t.lgID, 'teamID': t.teamID, 'franchID': t.franchID, 'divID': t.divID,
                      'G': 162, 'BPF': t.BPF, 'PPF': t.PPF, 'name': t['name'], 'teamIDBR': t.teamIDBR,
                      'teamIDlahman45': t.teamIDlahman45, 'teamIDretro': t.teamIDretro})

    pd.DataFrame(bat, columns=BAT_OUT).to_csv(f'{out}/Batting.csv', index=False)
    pd.DataFrame(pit, columns=PIT_OUT).to_csv(f'{out}/Pitching.csv', index=False)
    pd.DataFrame(app).to_csv(f'{out}/Appearances.csv', index=False)
    pd.DataFrame(teams).to_csv(f'{out}/Teams.csv', index=False)
    pd.DataFrame(newp).to_csv(f'{out}/People.csv', index=False)

    b, p_ = pd.DataFrame(bat), pd.DataFrame(pit)
    print(f'wrote {out}: {len(bat)} batting rows, {len(pit)} pitching rows, {len(app)} appearances, '
          f'{len(newp)} new people')
    print(f'sanity: league HR {b.HR.sum()} (batting) vs {p_.HR.sum()} (pitching); '
          f'ER {p_.ER.sum()}, IP {p_.IPouts.sum() / 3:.0f}, games per team ~{b.groupby("teamID").G.max().median():.0f}')
    if len(newp):
        print('new players (check IDs look right):', ', '.join(x['playerID'] for x in newp[:12]), '...')


if __name__ == '__main__':
    main()