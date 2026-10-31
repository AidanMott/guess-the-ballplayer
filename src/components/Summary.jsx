import React, { useEffect, useRef } from 'react';
import Avatar from './Avatar.jsx';
import { yearsLabel, formatCell } from '../lib/format.js';

function careerLine(entry, meta) {
  const parts = [];
  const pick = (tbl, cols) => {
    const row = tbl.find((r) => r.k === 'c');
    if (!row) return null;
    const v = (c) => row.v[cols.indexOf(c)];
    return { v, yrs: row.v[0] };
  };
  if (entry.bat) {
    const c = pick(entry.bat, meta.batCols);
    parts.push(`Career (${c.yrs}): ${c.v('G').toLocaleString()} G, ${formatCell('BA', c.v('BA'))}/${formatCell('OBP', c.v('OBP'))}/${formatCell('SLG', c.v('SLG'))}, ${c.v('HR')} HR, ${c.v('RBI')} RBI, ${c.v('H').toLocaleString()} H`);
  }
  if (entry.pit) {
    const c = pick(entry.pit, meta.pitCols);
    parts.push(`${entry.bat ? 'Pitching' : 'Career'} (${c.yrs}): ${c.v('W')}-${c.v('L')}, ${formatCell('ERA', c.v('ERA'))} ERA, ${c.v('SO').toLocaleString()} SO in ${formatCell('IP', c.v('IP'))} IP`);
  }
  return parts;
}

function awardTally(entry, meta) {
  const counts = {};
  const seen = new Set();
  for (const [key, cols] of [['bat', meta.batCols], ['pit', meta.pitCols]]) {
    for (const r of entry[key] || []) {
      if (r.k === 'x' || r.k === 'c' || r.k === 'm') continue;
      const yr = r.v[0];
      const aw = r.v[cols.indexOf('Awards')];
      if (!aw) continue;
      for (const a of aw.split(',')) {
        const tag = `${yr}:${a}`;
        if (seen.has(tag)) continue; // two-way players list awards on both tables
        seen.add(tag);
        const base = a.split('-')[0];
        const won = !a.includes('-') || a.endsWith('-1');
        if (base === 'AS') counts.AS = (counts.AS || 0) + 1;
        else if (won) counts[base] = (counts[base] || 0) + 1;
      }
    }
  }
  const names = { AS: 'All-Star', MVP: 'MVP', CYA: 'Cy Young', ROY: 'Rookie of the Year', GG: 'Gold Glove', SS: 'Silver Slugger' };
  return Object.keys(names).filter((k) => counts[k]).map((k) =>
    k === 'AS' ? `${counts[k]}× All-Star` : `${counts[k]}× ${names[k]}`);
}

function teamsPlayed(entry, meta) {
  const out = [];
  for (const [key, cols] of [['bat', meta.batCols], ['pit', meta.pitCols]]) {
    for (const r of entry[key] || []) {
      if (r.k !== 'y' && r.k !== 'x') continue;
      const t = r.v[cols.indexOf('Team')];
      if (!out.includes(t)) out.push(t);
    }
  }
  return out;
}

export default function Summary({ target, entry, meta, result, guesses, onNext }) {
  const box = useRef(null);
  // Bring the result card into view as soon as it appears.
  useEffect(() => { box.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, []);
  const bio = entry.bio;
  const won = result === 'won';
  const wrong = guesses.filter((g) => !g.correct).length;
  const awards = awardTally(entry, meta);
  const lines = careerLine(entry, meta);
  const bbUrl = bio.bbref ? `https://www.baseball-reference.com/players/${bio.bbref[0]}/${bio.bbref}.shtml` : null;
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const born = (() => {
    if (!bio.born) return null;
    const [y, m, d] = bio.born.split('-');
    return [m && MONTHS[m - 1], d && `${d},`, y].filter(Boolean).join(' ');
  })();
  const height = bio.ht ? `${Math.floor(bio.ht / 12)}′${bio.ht % 12}″` : null;

  return (
    <section ref={box} className={`panel summary ${won ? 'won' : 'lost'}`} aria-live="polite">
      <p className="verdict">
        {won
          ? `You got it${guesses.length === 1 ? ' on your first guess!' : ` in ${guesses.length} guesses!`}`
          : `You gave up after ${wrong} wrong ${wrong === 1 ? 'guess' : 'guesses'}.`}
      </p>
      <div className="who">
        <Avatar mlbam={target.m} name={target.n} size={88} />
        <div>
          <h2>{target.n}{bio.hof && <span className="hof" title="Baseball Hall of Fame">HOF</span>}</h2>
          <p className="muted">
            {yearsLabel(target)} · {target.pos} · {teamsPlayed(entry, meta).join(', ')}
          </p>
          <p className="muted small">
            {[born && `Born ${born}`, bio.city && `in ${[bio.city, bio.country].filter(Boolean).join(', ')}`,
              bio.bats && `Bats ${bio.bats}`, bio.throws && `Throws ${bio.throws}`, height].filter(Boolean).join(' · ')}
          </p>
        </div>
      </div>
      <ul className="facts">
        {lines.map((l) => <li key={l}>{l}</li>)}
        {awards.length > 0 && <li>{awards.join(' · ')}</li>}
      </ul>
      <div className="summary-actions">
        <button className="primary" onClick={onNext}>Pick a new player</button>
        {bbUrl && <a href={bbUrl} target="_blank" rel="noopener noreferrer">See {target.n} on Baseball-Reference ↗</a>}
      </div>
    </section>
  );
}