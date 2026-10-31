#!/usr/bin/env python3
"""
Build the RefGuess dataset from the Lahman database (+ Chadwick register for photos).

Outputs (to --out, default ../public/data):
  meta.json            column lists, franchise list, data year range
  players.json         compact index of every player (search + filters)
  shards/NN.json       full BR-style tables, 128 shards keyed by crc32(playerID)

Usage:
  python build_data.py --lahman /path/to/Lahman --register /path/to/register \
                       [--extra-dir DIR] [--war-bat FILE] [--war-pit FILE] [--active-file FILE]

  --lahman    clone of https://github.com/cdalzell/Lahman (uses data/*.RData)
  --register  clone of https://github.com/chadwickbureau/register (data/people-*.csv)
  --extra-dir optional folder of Lahman-schema CSVs (Batting.csv, Pitching.csv, Appearances.csv,
              AwardsPlayers.csv, AllstarFull.csv, Teams.csv, People.csv) appended to the base data, e.g. a 2026 season
  --war-bat / --war-pit  optional Baseball-Reference bulk WAR files (war_daily_bat.txt / war_daily_pitch.txt)
  --active-file  optional text file of bbref IDs (one per line) to treat as "active"
                 (default: anyone who played in the latest season in the data)
"""
import argparse, glob, json, os, zlib
from collections import defaultdict
import numpy as np
import pandas as pd
from rdata import read_rdata

# ---------------------------------------------------------------- column definitions
# NOTE: rOBA and Rbat+ are intentionally omitted (not derivable from Lahman); WAR is blank
#       unless a bWAR file is supplied.
BAT_COLS = ['Season', 'Age', 'Team', 'Lg', 'WAR', 'G', 'PA', 'AB', 'R', 'H', '2B', '3B', 'HR', 'RBI', 'SB', 'CS',
            'BB', 'SO', 'BA', 'OBP', 'SLG', 'OPS', 'OPS+', 'TB', 'GIDP', 'HBP', 'SH', 'SF', 'IBB', 'Pos', 'Awards']
PIT_COLS = ['Season', 'Age', 'Team', 'Lg', 'WAR', 'W', 'L', 'W-L%', 'ERA', 'G', 'GS', 'GF', 'CG', 'SHO', 'SV', 'IP',
            'H', 'R', 'ER', 'HR', 'BB', 'IBB', 'SO', 'HBP', 'BK', 'WP', 'BF', 'ERA+', 'FIP', 'WHIP', 'H9', 'HR9',
            'BB9', 'SO9', 'SO/BB', 'Awards']
INTERNAL = {'2B': 'X2B', '3B': 'X3B', 'OPS+': 'OPSp', 'BF': 'BFP', 'IP': 'IPouts', 'W-L%': 'WLpct',
            'ERA+': 'ERAp', 'SO/BB': 'SObb'}

BAT_ADD = ['G', 'PA', 'AB', 'R', 'H', 'X2B', 'X3B', 'HR', 'RBI', 'SB', 'CS', 'BB', 'SO', 'IBB', 'HBP', 'SH', 'SF',
           'GIDP', 'TB', 'WAR', 'wa_lgobp', 'wa_lgslg', 'wa_pf']
PIT_ADD = ['W', 'L', 'G', 'GS', 'GF', 'CG', 'SHO', 'SV', 'IPouts', 'H', 'R', 'ER', 'HR', 'BB', 'IBB', 'SO', 'HBP',
           'BK', 'WP', 'BFP', 'WAR', 'wi_lgera', 'wi_cfip', 'wi_ppf']
POS_COLS = [('G_p', '1'), ('G_c', '2'), ('G_1b', '3'), ('G_2b', '4'), ('G_3b', '5'), ('G_ss', '6'),
            ('G_lf', '7'), ('G_cf', '8'), ('G_rf', '9'), ('G_dh', 'D')]
POS_NAMES = {'1': 'P', '2': 'C', '3': '1B', '4': '2B', '5': '3B', '6': 'SS', '7': 'LF', '8': 'CF', '9': 'RF', 'D': 'DH'}

# (internal column, direction, kind)   kind: count = raw max (>0), rate = needs qualification
BAT_LEADERS = [(c, 'hi', 'count') for c in ['G', 'PA', 'AB', 'R', 'H', 'X2B', 'X3B', 'HR', 'RBI', 'SB', 'CS', 'BB',
                                           'SO', 'TB', 'GIDP', 'HBP', 'SH', 'SF', 'IBB', 'WAR']] + \
              [(c, 'hi', 'rate') for c in ['BA', 'OBP', 'SLG', 'OPS', 'OPSp']]
PIT_LEADERS = [(c, 'hi', 'count') for c in ['W', 'L', 'G', 'GS', 'GF', 'CG', 'SHO', 'SV', 'IPouts', 'H', 'R', 'ER',
                                           'HR', 'BB', 'IBB', 'SO', 'HBP', 'BK', 'WP', 'BFP', 'WAR']] + \
              [(c, 'hi', 'rate') for c in ['WLpct', 'ERAp', 'SO9', 'SObb']] + \
              [(c, 'lo', 'rate') for c in ['ERA', 'FIP', 'WHIP', 'H9', 'HR9', 'BB9']]

# Lahman's franchise names lag behind name changes; these are the current display names.
NAME_OVERRIDES = {'CLE': 'Cleveland Guardians', 'FLA': 'Miami Marlins', 'ANA': 'Los Angeles Angels', 'OAK': 'Athletics'}

# team abbreviations that share one per-team career summary row
TEAM_GROUP = {'OAK': 'ATH'}

CAREER_QUAL_PA = 3000      # career rate-stat qualification for records / active leaders
CAREER_QUAL_OUTS = 3000    # = 1000 IP
N_SHARDS = 128


def load(lahman, name, extra_dir=None):
    df = list(read_rdata(os.path.join(lahman, 'data', name + '.RData')).values())[0]
    if extra_dir:
        p = os.path.join(extra_dir, name + '.csv')
        if os.path.exists(p):
            ex = pd.read_csv(p)
            print(f'  + {len(ex)} extra rows for {name}')
            df = pd.concat([df, ex], ignore_index=True)
    return df


def shard_of(pid):
    return zlib.crc32(pid.encode()) % N_SHARDS


def jv(x, nd=4):
    """JSON-safe scalar."""
    if x is None:
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        if not np.isfinite(x):
            return None
        return int(x) if float(x).is_integer() and abs(x) < 1e12 else round(float(x), nd)
    if isinstance(x, (str, int)):
        return x
    return None if pd.isna(x) else x


# ---------------------------------------------------------------- derived stats
def derive_bat(d):
    ab = d.AB.where(d.AB > 0)
    hbp, sf = d.HBP.fillna(0), d.SF.fillna(0)
    den = (d.AB + d.BB + hbp + sf)
    d['BA'] = d.H / ab
    d['OBP'] = (d.H + d.BB + hbp) / den.where(den > 0)
    d['SLG'] = d.TB / ab
    d['OPS'] = d.OBP + d.SLG
    pa = d.PA.where(d.PA > 0)
    lo, ls, pf = d.wa_lgobp / pa, d.wa_lgslg / pa, d.wa_pf / pa
    # Hitters play ~half their games at home, so the park effect is applied at half strength.
    # (Tested against known BR values; ERA+ below uses the full factor, which matches BR.)
    d['OPSp'] = (100 * (d.OBP / lo + d.SLG / ls - 1) / (1 + (pf / 100 - 1) / 2)).round()
    return d


def derive_pit(d):
    o = d.IPouts.where(d.IPouts > 0)
    dec = (d.W + d.L).where((d.W + d.L) > 0)
    d['WLpct'] = d.W / dec
    d['ERA'] = 27 * d.ER / o
    d['WHIP'] = 3 * (d.BB + d.H) / o
    d['H9'], d['HR9'], d['BB9'], d['SO9'] = 27 * d.H / o, 27 * d.HR / o, 27 * d.BB / o, 27 * d.SO / o
    d['SObb'] = d.SO / d.BB.where(d.BB > 0)
    ip = o / 3
    d['FIP'] = (13 * d.HR + 3 * (d.BB + d.HBP.fillna(0)) - 2 * d.SO) / ip + d.wi_cfip / o
    lgera, ppf = d.wi_lgera / o, d.wi_ppf / o
    d['ERAp'] = (100 * lgera * (ppf / 100) / d.ERA.where(d.ERA > 0)).round()
    return d


def aggregate(df, keys, add_cols):
    g = df.groupby(keys, sort=False)
    out = g[add_cols].sum(min_count=1)
    out['lg_first'] = g.lgID.first()
    out['lg_n'] = g.lgID.nunique()
    out['n_tm'] = g.teamID.nunique()
    out['tG'] = g.tG.max()
    return out.reset_index()


# ---------------------------------------------------------------- positions / awards
def pos_string(gd, tG, ph, pr):
    """Baseball-Reference 'Pos' notation.

    - positions are listed in order of games played at each (1=P 2=C 3=1B 4=2B 5=3B 6=SS 7=LF 8=CF 9=RF D=DH)
    - '*' marks a position where the player appeared in at least 2/3 of team games (a season or a career)
    - positions after the '/' are ones with fewer than ten games
    - 'H' is games as a pinch hitter or pinch runner
    """
    gd = dict(gd)
    h = (ph or 0) + (pr or 0)
    if h > 0:
        gd['H'] = h
    items = sorted(((g, c) for c, g in gd.items() if g and g > 0), key=lambda x: -x[0])  # stable on ties
    if not items:
        return None
    main = ''.join(('*' if (tG and c != 'H' and g >= (2 / 3) * tG) else '') + c for g, c in items if g >= 10)
    minor = ''.join(c for g, c in items if g < 10)
    return main + ('/' + minor if minor else '')


AWARD_ORDER = {'AS': 0, 'MVP': 1, 'CYA': 2, 'ROY': 3, 'GG': 4, 'SS': 5}


def build_awards(aw, share, asg):
    out = defaultdict(dict)
    sh = share.copy()
    sh['rank'] = sh.groupby(['awardID', 'yearID', 'lgID']).pointsWon.rank(method='min', ascending=False)
    short = {'Most Valuable Player': 'MVP', 'Cy Young Award': 'CYA', 'Rookie of the Year': 'ROY'}
    for r in sh.itertuples():
        k = short.get(r.awardID)
        if k:
            out[(r.playerID, int(r.yearID))][k] = f'{k}-{int(r.rank)}'
    for r in aw.itertuples():
        yr = int(r.yearID)
        k = short.get(r.awardID)
        if k and k not in out[(r.playerID, yr)]:
            out[(r.playerID, yr)][k] = f'{k}-1'
        elif r.awardID == 'Gold Glove':
            out[(r.playerID, yr)]['GG'] = 'GG'
        elif r.awardID == 'Silver Slugger':
            out[(r.playerID, yr)]['SS'] = 'SS'
    for r in asg.drop_duplicates(['playerID', 'yearID']).itertuples():
        out[(r.playerID, int(r.yearID))]['AS'] = 'AS'
    res = {}
    for key, d in out.items():
        res[key] = ','.join(v for k, v in sorted(d.items(), key=lambda kv: AWARD_ORDER.get(kv[0], 9)))
    return res


# ---------------------------------------------------------------- leaders
def league_lines(df, add_cols):
    """One line per (player, year, league): everything a player did within that league."""
    g = df.groupby(['playerID', 'yearID', 'lgID'], sort=False)
    out = g[add_cols].sum(min_count=1)
    out['n_st'] = g.stint.nunique()
    out['stint1'] = g.stint.first()
    return out.reset_index()


def season_leaders(L, S, specs, qualcol, mult, lgG, yrG):
    """Leader flags keyed by the row that earns them.

    League leaders (bold) are decided on each player's line *within a league*, so a player traded
    between leagues can still lead the league he qualified in (and cannot lead the one he left).
    The bold goes on: the season row if he stayed in one league, otherwise his single team row in
    that league (no row is marked if he had several teams in that league and also left it).
    MLB leaders (italic) are decided on full-season totals and go on the season row.

    Returns {(pid, year, 'tot' | stint_number): {col: 'b'|'i'|'bi'}}.
    """
    lg_n = S.set_index(['playerID', 'yearID']).lg_n.to_dict()
    L = L.copy()
    L['_lgG'] = [lgG.get((y, l), 162) for y, l in zip(L.yearID, L.lgID)]
    S = S.copy()
    S['_yG'] = S.yearID.map(yrG).fillna(162)
    flags = defaultdict(lambda: defaultdict(set))
    for scope in ('lg', 'mlb'):
        sub = L if scope == 'lg' else S
        keys = ['yearID', 'lgID'] if scope == 'lg' else ['yearID']
        thr = mult * (sub._lgG if scope == 'lg' else sub._yG)
        for col, dirn, kind in specs:
            v = sub[col]
            ok = v.notna() & ((sub[qualcol] >= thr) if kind == 'rate' else (v > 0))
            cand = sub[ok]
            if cand.empty:
                continue
            ext = cand.groupby(keys)[col].transform('max' if dirn == 'hi' else 'min')
            hit = cand[np.isclose(cand[col], ext, rtol=0, atol=1e-9)]
            if scope == 'mlb':
                for pid, yr in zip(hit.playerID, hit.yearID):
                    flags[(pid, int(yr), 'tot')][col].add('i')
            else:
                for r in hit.itertuples():
                    yr = int(r.yearID)
                    if lg_n.get((r.playerID, r.yearID), 1) == 1:
                        flags[(r.playerID, yr, 'tot')][col].add('b')
                    elif r.n_st == 1:
                        flags[(r.playerID, yr, int(r.stint1))][col].add('b')
    return {k: {c: ''.join(sorted(m)) for c, m in d.items()} for k, d in flags.items()}


def career_leaders(C, specs, qualcol, qual, active_ids):
    """Return {pid: {col: 'g'|'a'}}: g = all-time record, a = active leader."""
    flags = defaultdict(dict)
    for col, dirn, kind in specs:
        ok = C[col].notna() & ((C[qualcol] >= qual) if kind == 'rate' else (C[col] > 0))
        cand = C[ok]
        if cand.empty:
            continue
        f = (lambda s: s.max()) if dirn == 'hi' else (lambda s: s.min())
        best = f(cand[col])
        for pid in cand.playerID[np.isclose(cand[col], best, rtol=0, atol=1e-9)]:
            flags[pid][col] = 'g'
        act = cand[cand.playerID.isin(active_ids)]
        if not act.empty:
            ab = f(act[col])
            for pid in act.playerID[np.isclose(act[col], ab, rtol=0, atol=1e-9)]:
                flags[pid].setdefault(col, 'a')
    return flags


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lahman', required=True)
    ap.add_argument('--register', required=True)
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), '..', 'public', 'data'))
    ap.add_argument('--extra-dir')
    ap.add_argument('--war-bat')
    ap.add_argument('--war-pit')
    ap.add_argument('--active-file')
    args = ap.parse_args()
    ex = args.extra_dir

    print('loading Lahman...')
    people = load(args.lahman, 'People', ex)
    bat = load(args.lahman, 'Batting', ex)
    pit = load(args.lahman, 'Pitching', ex)
    app = load(args.lahman, 'Appearances', ex)
    teams = load(args.lahman, 'Teams', ex)
    fr = load(args.lahman, 'TeamsFranchises')
    awp = load(args.lahman, 'AwardsPlayers', ex)
    aws = load(args.lahman, 'AwardsSharePlayers')
    asg = load(args.lahman, 'AllstarFull', ex)
    hof = load(args.lahman, 'HallOfFame')
    last_year = int(max(bat.yearID.max(), pit.yearID.max()))
    print('  latest season in data:', last_year)

    # ---- team lookups (also tolerate seasons missing from Teams)
    # current league/division per franchise (used to group the team picker)
    fr_div = (teams[teams.yearID == last_year].drop_duplicates('franchID')
              .set_index('franchID')[['lgID', 'divID']].to_dict('index'))
    teams = teams[['yearID', 'lgID', 'teamID', 'franchID', 'G', 'BPF', 'PPF', 'teamIDBR']].rename(columns={'G': 'tG'})
    teams = teams.drop_duplicates(['yearID', 'teamID'])
    lgG = teams.groupby(['yearID', 'lgID']).tG.max().to_dict()
    yrG = teams.groupby('yearID').tG.max().to_dict()

    def prep(df):
        d = df.merge(teams.drop(columns=['lgID']), on=['yearID', 'teamID'], how='left')
        d['TeamBR'] = d.teamIDBR.fillna(d.teamID)
        d['tG'] = d.tG.fillna(162)
        d['BPF'] = d.BPF.fillna(100)
        d['PPF'] = d.PPF.fillna(100)
        return d

    # ---- people, ages
    people = people.drop_duplicates('playerID', keep='first').set_index('playerID')
    bio_year, bio_m, bio_d = people.birthYear, people.birthMonth, people.birthDay

    def age_of(pids, years):
        by, bm, bd = bio_year.reindex(pids).values, bio_m.reindex(pids).values, bio_d.reindex(pids).values
        late = (bm > 6) | ((bm == 6) & (bd > 30))
        return years - by - np.where(late, 1, 0)

    # ---- pitcher-years (excluded from league batting environment)
    pi = app.groupby(['playerID', 'yearID'])[['G_p', 'G_all']].sum()
    pi['isp'] = (pi.G_all > 0) & (pi.G_p / pi.G_all.where(pi.G_all > 0) >= 0.5)

    # ---- BATTING
    print('batting...')
    b = prep(bat)
    for c in ['G', 'AB', 'R', 'H', 'X2B', 'X3B', 'HR', 'RBI', 'SB', 'CS', 'BB', 'SO', 'IBB', 'HBP', 'SH', 'SF', 'GIDP']:
        b[c] = pd.to_numeric(b[c], errors='coerce')
    b['PA'] = b[['AB', 'BB', 'HBP', 'SH', 'SF']].fillna(0).sum(axis=1)
    b['TB'] = b.H.fillna(0) + b.X2B.fillna(0) + 2 * b.X3B.fillna(0) + 3 * b.HR.fillna(0)
    b = b.merge(pi.isp.reset_index(), on=['playerID', 'yearID'], how='left')
    b['isp'] = b.isp.fillna(False).astype(bool)
    nb = b[~b.isp]
    lgb = nb.groupby(['yearID', 'lgID'])[['AB', 'H', 'BB', 'HBP', 'SF', 'TB']].sum()
    lgb['lgobp'] = (lgb.H + lgb.BB + lgb.HBP) / (lgb.AB + lgb.BB + lgb.HBP + lgb.SF)
    lgb['lgslg'] = lgb.TB / lgb.AB
    b = b.merge(lgb[['lgobp', 'lgslg']].reset_index(), on=['yearID', 'lgID'], how='left')
    b['wa_lgobp'], b['wa_lgslg'], b['wa_pf'] = b.lgobp * b.PA, b.lgslg * b.PA, b.BPF * b.PA
    b['WAR'] = np.nan

    # ---- PITCHING
    print('pitching...')
    p = prep(pit)
    for c in ['W', 'L', 'G', 'GS', 'GF', 'CG', 'SHO', 'SV', 'IPouts', 'H', 'R', 'ER', 'HR', 'BB', 'IBB', 'SO',
              'HBP', 'BK', 'WP', 'BFP']:
        p[c] = pd.to_numeric(p[c], errors='coerce')
    lgp = p.groupby(['yearID', 'lgID'])[['ER', 'IPouts', 'HR', 'BB', 'HBP', 'SO']].sum()
    lgp['lgera'] = 27 * lgp.ER / lgp.IPouts
    lgp['cfip'] = lgp.lgera - (13 * lgp.HR + 3 * (lgp.BB + lgp.HBP) - 2 * lgp.SO) / (lgp.IPouts / 3)
    p = p.merge(lgp[['lgera', 'cfip']].reset_index(), on=['yearID', 'lgID'], how='left')
    p['wi_lgera'], p['wi_cfip'], p['wi_ppf'] = p.lgera * p.IPouts, p.cfip * p.IPouts, p.PPF * p.IPouts
    p['WAR'] = np.nan

    # ---- optional bWAR
    people_bbref = people.bbrefID
    bb2lah = {v: k for k, v in people_bbref.dropna().items()}

    def merge_war(df, path, pitcher):
        if not path:
            return df
        w = pd.read_csv(path, low_memory=False)
        w = w[w.pitcher == ('Y' if pitcher else 'N')] if 'pitcher' in w.columns else w
        w['playerID'] = w.player_ID.map(bb2lah)
        w = w.dropna(subset=['playerID'])
        w['WARv'] = pd.to_numeric(w.WAR, errors='coerce')
        w = w.groupby(['playerID', 'year_ID', 'stint_ID']).WARv.sum(min_count=1).reset_index()
        w.columns = ['playerID', 'yearID', 'stint', 'WARv']
        df = df.merge(w, on=['playerID', 'yearID', 'stint'], how='left')
        df['WAR'] = df.WARv
        print(f'  WAR merged for {df.WAR.notna().sum()} rows')
        return df.drop(columns='WARv')

    b = merge_war(b, args.war_bat, False)
    p = merge_war(p, args.war_pit, True)

    # ---- positions per (player, year, team): attach to first stint only
    gcols = [c for c, _ in POS_COLS] + ['G_ph', 'G_pr']
    ap2 = app.groupby(['playerID', 'yearID', 'teamID'], as_index=False)[gcols].sum()
    b['_first'] = b.groupby(['playerID', 'yearID', 'teamID']).cumcount() == 0
    b = b.merge(ap2, on=['playerID', 'yearID', 'teamID'], how='left')
    for c in gcols:
        b[c] = np.where(b._first, b[c], 0)

    # ---- which tables does each player get?
    cap = app.groupby('playerID')[['G_p', 'G_all', 'G_c', 'G_1b', 'G_2b', 'G_3b', 'G_ss', 'G_lf', 'G_cf', 'G_rf',
                                   'G_dh']].sum()
    cap['field'] = cap[['G_c', 'G_1b', 'G_2b', 'G_3b', 'G_ss', 'G_lf', 'G_cf', 'G_rf', 'G_dh']].sum(axis=1)
    car_pa = b.groupby('playerID').PA.sum()
    car_outs = p.groupby('playerID').IPouts.sum()
    kinds = {}
    for pid in set(b.playerID) | set(p.playerID):
        pa, outs = car_pa.get(pid, 0), car_outs.get(pid, 0)
        a = cap.loc[pid] if pid in cap.index else None
        gall, gp, fld = (a.G_all, a.G_p, a.field) if a is not None else (0, 0, 0)
        if outs >= 600 and pa >= 1000 and fld >= 300:
            kinds[pid] = 'bp'
        elif outs > 0 and (pa == 0 or (gall > 0 and gp / gall >= 0.5) or (gall == 0 and outs > pa)):
            kinds[pid] = 'p'
        elif pa > 0:
            kinds[pid] = 'b'
        elif outs > 0:
            kinds[pid] = 'p'
    print('  players:', len(kinds), ' two-way:', sum(v == 'bp' for v in kinds.values()))
    bat_players = {k for k, v in kinds.items() if 'b' in v}
    pit_players = {k for k, v in kinds.items() if 'p' in v}
    b = b[b.playerID.isin(bat_players)].copy()
    p = p[p.playerID.isin(pit_players)].copy()

    # ---- derive stint rows + season totals
    b = derive_bat(b)
    p = derive_pit(p)
    bS = aggregate(b, ['playerID', 'yearID'], BAT_ADD)
    pS = aggregate(p, ['playerID', 'yearID'], PIT_ADD)
    bS = derive_bat(bS)
    pS = derive_pit(pS)
    bC = derive_bat(b.groupby('playerID')[BAT_ADD].sum(min_count=1).reset_index())
    pC = derive_pit(p.groupby('playerID')[PIT_ADD].sum(min_count=1).reset_index())

    # ---- leaders / records
    print('leaders...')
    bL = derive_bat(league_lines(b, BAT_ADD))
    pL = derive_pit(league_lines(p, PIT_ADD))
    bflags = season_leaders(bL, bS, BAT_LEADERS, 'PA', 3.1, lgG, yrG)
    pflags = season_leaders(pL, pS, PIT_LEADERS, 'IPouts', 3.0, lgG, yrG)
    last_by = pd.concat([b[['playerID', 'yearID']], p[['playerID', 'yearID']]]).groupby('playerID').yearID.max()
    active_ids = set(last_by[last_by >= last_year].index)
    if args.active_file:
        extra_act = {bb2lah.get(x.strip()) for x in open(args.active_file) if x.strip()}
        active_ids = {x for x in extra_act if x}
    print('  active players:', len(active_ids))
    bcf = career_leaders(bC, BAT_LEADERS, 'PA', CAREER_QUAL_PA, active_ids)
    pcf = career_leaders(pC, PIT_LEADERS, 'IPouts', CAREER_QUAL_OUTS, active_ids)

    # ---- awards
    awards = build_awards(awp, aws, asg)
    hof_ids = set(hof[(hof.inducted == 'Y') & (hof.category == 'Player')].playerID)

    # ---- photos
    print('register...')
    reg = pd.concat([pd.read_csv(f, usecols=['key_mlbam', 'key_bbref', 'key_retro'], dtype=str)
                     for f in glob.glob(os.path.join(args.register, 'data', 'people-*.csv'))])
    m_bb = reg.dropna(subset=['key_bbref', 'key_mlbam']).drop_duplicates('key_bbref').set_index('key_bbref').key_mlbam
    m_rt = reg.dropna(subset=['key_retro', 'key_mlbam']).drop_duplicates('key_retro').set_index('key_retro').key_mlbam

    # ---- row emitters
    def cols_internal(cols):
        return [INTERNAL.get(c, c) for c in cols]

    def make_emitters(kind):
        cols = BAT_COLS if kind == 'b' else PIT_COLS
        icols = cols_internal(cols)
        return cols, icols

    def row_vals(r, kind, icols, season, team, lg, age, awardstr, pos, label_cols=None):
        out = []
        for ic in icols:
            if ic == 'Season':
                out.append(season)
            elif ic == 'Age':
                out.append(jv(age))
            elif ic == 'Team':
                out.append(team)
            elif ic == 'Lg':
                out.append(lg)
            elif ic == 'Awards':
                out.append(awardstr or None)
            elif ic == 'Pos':
                out.append(pos)
            elif ic == 'WAR':
                out.append(jv(r.get('WAR'), 1))
            else:
                out.append(jv(r.get(ic)))
        return out

    def flags_to_idx(fl, icols):
        if not fl:
            return None
        res = {}
        for i, ic in enumerate(icols):
            if ic in fl and fl[ic]:
                res[str(i)] = fl[ic]
        return res or None

    def build_table(pid, kind, stints, seasons, careerrow, sflags, cflag, tbl_cache):
        cols, icols = tbl_cache
        rows = []
        # group stints by year
        by_year = defaultdict(list)
        for r in stints:
            by_year[int(r['yearID'])].append(r)
        for r in seasons:
            yr = int(r['yearID'])
            age = r.get('age')
            aw = awards.get((pid, yr))
            ss = by_year[yr]
            first = ss[0]
            pos = None
            if kind == 'b':
                gd = {c: sum((x.get(g) or 0) for x in ss) for g, c in POS_COLS}
                pos = pos_string(gd, r['tG'], sum((x.get('G_ph') or 0) for x in ss), sum((x.get('G_pr') or 0) for x in ss))
            fl = flags_to_idx(sflags.get((pid, yr, 'tot')), icols)
            if r['n_tm'] > 1 or len(ss) > 1:
                lg = r['lg_first'] if r['lg_n'] == 1 else 'MLB'
                rows.append({'k': 'T', 'v': row_vals(r, kind, icols, yr, f"{r['n_tm']}TM", lg, age, aw, pos),
                             **({'f': fl} if fl else {})})
                for x in ss:
                    xp = None
                    if kind == 'b':
                        xp = pos_string({c: (x.get(g) or 0) for g, c in POS_COLS}, x['tG'], x.get('G_ph'), x.get('G_pr'))
                    xfl = flags_to_idx(sflags.get((pid, yr, int(x['stint']))), icols)
                    rows.append({'k': 'x', 'v': row_vals(x, kind, icols, yr, x['TeamBR'], x['lgID'], age, None, xp),
                                 **({'f': xfl} if xfl else {})})
            else:
                x = ss[0]
                rows.append({'k': 'y', 'v': row_vals(r, kind, icols, yr, x['TeamBR'], x['lgID'], age, aw, pos),
                             **({'f': fl} if fl else {})})
        # career
        nyrs = len(seasons)
        cf = flags_to_idx(cflag, icols)
        cpos = None
        if kind == 'b':
            cpos = pos_string({c: sum((x.get(g) or 0) for x in stints) for g, c in POS_COLS},
                              sum(r['tG'] for r in seasons),
                              sum((x.get('G_ph') or 0) for x in stints), sum((x.get('G_pr') or 0) for x in stints))
        rows.append({'k': 'c', 'v': row_vals(careerrow, kind, icols, f'{nyrs} Yr' + ('s' if nyrs != 1 else ''),
                                             None, None, None, None, cpos), **({'f': cf} if cf else {})})
        # per-team career rows
        tm = defaultdict(list)
        for x in stints:
            tm[TEAM_GROUP.get(x['TeamBR'], x['TeamBR'])].append(x)   # OAK + ATH are one franchise: one summary row
        if len(tm) > 1:
            add = BAT_ADD if kind == 'b' else PIT_ADD
            for t, xs in sorted(tm.items(), key=lambda kv: min(int(x['yearID']) for x in kv[1])):
                tdf = pd.DataFrame(xs)
                agg = tdf[add].sum(min_count=1).to_frame().T
                agg = derive_bat(agg) if kind == 'b' else derive_pit(agg)
                n = tdf.yearID.nunique()
                tpos = None
                if kind == 'b':
                    tpos = pos_string({c: sum((x.get(g) or 0) for x in xs) for g, c in POS_COLS},
                                      sum({int(x['yearID']): x['tG'] for x in xs}.values()),
                                      sum((x.get('G_ph') or 0) for x in xs), sum((x.get('G_pr') or 0) for x in xs))
                t = max(xs, key=lambda x: int(x['yearID']))['TeamBR']   # label with the most recent abbreviation
                rows.append({'k': 'm', 'v': row_vals(agg.iloc[0].to_dict(), kind, icols, None,
                                                     f'{t} ({n} yr' + ('s' if n != 1 else '') + ')', None, None,
                                                     None, tpos)})
        return rows

    bcache = make_emitters('b')
    pcache = make_emitters('p')

    def group_records(df, need_pos):
        out = defaultdict(list)
        for r in df.to_dict('records'):
            out[r['playerID']].append(r)
        return out

    print('assembling players...')
    b_st = group_records(b.sort_values(['playerID', 'yearID', 'stint']), True)
    p_st = group_records(p.sort_values(['playerID', 'yearID', 'stint']), False)
    bS['age'] = age_of(bS.playerID.values, bS.yearID.values)
    pS['age'] = age_of(pS.playerID.values, pS.yearID.values)
    b_se = group_records(bS.sort_values(['playerID', 'yearID']), False)
    p_se = group_records(pS.sort_values(['playerID', 'yearID']), False)
    b_ca = {r['playerID']: r for r in bC.to_dict('records')}
    p_ca = {r['playerID']: r for r in pC.to_dict('records')}
    fr_names = fr.set_index('franchID').franchName.to_dict()
    fr_active = fr.set_index('franchID').active.to_dict()

    shards = [dict() for _ in range(N_SHARDS)]
    index = []
    for pid, kind in kinds.items():
        if pid not in people.index:
            continue
        pr = people.loc[pid]
        name = f"{pr.nameFirst or ''} {pr.nameLast or ''}".strip()
        entry = {}
        years, frs = set(), set()
        pa_c = ip_c = gp_c = 0
        pos_main = None
        hit_pos = None
        season_pos = set()
        if 'b' in kind and pid in b_st:
            entry['bat'] = build_table(pid, 'b', b_st[pid], b_se[pid], b_ca[pid], bflags, bcf.get(pid, {}), bcache)
            years |= {int(r['yearID']) for r in b_st[pid]}
            frs |= {r['franchID'] for r in b_st[pid] if isinstance(r['franchID'], str)}
            pa_c = int(b_ca[pid]['PA'] or 0)
            # primary position over career
            tot = defaultdict(float)
            for r in b_st[pid]:
                for g, c in POS_COLS:
                    tot[c] += r.get(g) or 0
            if kind == 'b':
                if tot and max(tot.values()) > 0:
                    pos_main = POS_NAMES[max(tot, key=tot.get)]
                else:
                    pos_main = 'PH'
            else:  # two-way: show as hitter position excluding P
                tot.pop('1', None)
                pos_main = POS_NAMES[max(tot, key=tot.get)] if tot and max(tot.values()) > 0 else 'DH'
            hit_pos = pos_main  # primary hitting position, used by the position filter
            # every position that was his most-played position in at least one season (position filter)
            by_year = defaultdict(lambda: defaultdict(float))
            for r in b_st[pid]:
                for g, c in POS_COLS:
                    if c != '1':  # pitching appearances by position players don't count
                        by_year[int(r['yearID'])][c] += r.get(g) or 0
            for yg in by_year.values():
                top = max(yg.values()) if yg else 0
                if top > 0:
                    season_pos |= {POS_NAMES[c] for c, v in yg.items() if v == top}
        if 'p' in kind and pid in p_st:
            entry['pit'] = build_table(pid, 'p', p_st[pid], p_se[pid], p_ca[pid], pflags, pcf.get(pid, {}), pcache)
            years |= {int(r['yearID']) for r in p_st[pid]}
            frs |= {r['franchID'] for r in p_st[pid] if isinstance(r['franchID'], str)}
            ip_c = round(float(p_ca[pid]['IPouts'] or 0) / 3, 1)
            gp_c = int(p_ca[pid]['G'] or 0)  # games pitched
            season_pos.add('P')
            if kind == 'p':
                pos_main = 'P'
            else:
                pos_main = (pos_main or '') + '/P'
        if not entry or not years:
            continue
        g_all = int(cap.G_all.get(pid, 0)) if pid in cap.index else 0
        mlbam = m_bb.get(pr.bbrefID) if isinstance(pr.bbrefID, str) else None
        if mlbam is None and isinstance(pr.retroID, str):
            mlbam = m_rt.get(pr.retroID)
        bd = None
        if pd.notna(pr.birthYear):
            bd = '-'.join(str(int(x)) if pd.notna(x) else '' for x in (pr.birthYear, pr.birthMonth, pr.birthDay))
        entry['bio'] = {
            'name': name, 'bbref': pr.bbrefID if isinstance(pr.bbrefID, str) else None,
            'born': bd, 'city': pr.birthCity if isinstance(pr.birthCity, str) else None,
            'country': pr.birthCountry if isinstance(pr.birthCountry, str) else None,
            'bats': pr.bats if isinstance(pr.bats, str) else None,
            'throws': pr.throws if isinstance(pr.throws, str) else None,
            'ht': jv(pr.height), 'wt': jv(pr.weight), 'hof': pid in hof_ids,
            'debut': str(pr.debut)[:10] if pd.notna(pr.debut) else None,
            'final': str(pr.finalGame)[:10] if pd.notna(pr.finalGame) else None,
            'died': jv(pr.deathYear) if pd.notna(pr.deathYear) else None,
        }
        # "notable": something in the Awards column, or a bold/italic (league / MLB leader) season stat
        notable = 0
        for key in ('bat', 'pit'):
            for r in entry.get(key) or []:
                if r['k'] in ('y', 'T', 'x') and (r['v'][-1] or any(v in ('b', 'i', 'bi') for v in (r.get('f') or {}).values())):
                    notable = 1
        shards[shard_of(pid)][pid] = entry
        ys = sorted(years)
        index.append({'i': pid, 'n': name, 'm': mlbam, 'y': [ys[0], ys[-1]], 'ys': ys, 't': kind, 'pos': pos_main,
                      'pa': pa_c, 'ip': ip_c, 'gp': gp_c, 'hp': hit_pos, 'ps': sorted(season_pos), 'g': g_all, 'f': sorted(frs), 'a': 1 if pid in active_ids else 0, 'nt': notable})

    # ---- write
    out = os.path.abspath(args.out)
    os.makedirs(os.path.join(out, 'shards'), exist_ok=True)
    for f in glob.glob(os.path.join(out, 'shards', '*.json')):
        os.remove(f)
    for i, s in enumerate(shards):
        with open(os.path.join(out, 'shards', f'{i:03d}.json'), 'w') as fh:
            json.dump(s, fh, separators=(',', ':'), allow_nan=False)
    index.sort(key=lambda r: r['n'])
    with open(os.path.join(out, 'players.json'), 'w') as fh:
        json.dump(index, fh, separators=(',', ':'), allow_nan=False)
    used_fr = sorted({f for r in index for f in r['f']})
    meta = {
        'batCols': BAT_COLS, 'pitCols': PIT_COLS, 'nShards': N_SHARDS, 'lastSeason': last_year,
        'franchises': [{'id': f, 'name': NAME_OVERRIDES.get(f, fr_names.get(f, f)), 'active': fr_active.get(f) == 'Y',
                        'lg': (fr_div.get(f) or {}).get('lgID'), 'div': (fr_div.get(f) or {}).get('divID')}
                       for f in used_fr],
        'warLoaded': bool(args.war_bat or args.war_pit),
        'minYear': int(min(r['y'][0] for r in index)),
    }
    with open(os.path.join(out, 'meta.json'), 'w') as fh:
        json.dump(meta, fh, separators=(',', ':'))
    print(f'done: {len(index)} players -> {out}')


if __name__ == '__main__':
    main()