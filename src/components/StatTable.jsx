import React, { useEffect, useRef, useState } from 'react';
import { teamColor } from '../lib/teamColors.js';
import { formatCell, headerLabel, APPROX_COLS, TOOLTIPS } from '../lib/format.js';

// Awards cell: a first-place finish in a ranked award (MVP-1, CYA-1, ROY-1) is bold.
function Awards({ value }) {
  return value.split(',').map((a, i) => (
    <React.Fragment key={i}>
      {i > 0 && ','}
      {/^(MVP|CYA|ROY)-1$/.test(a) ? <b>{a}</b> : a}
    </React.Fragment>
  ));
}

// Career and per-team career rows merge Season, Age, Team and Lg into one label cell.
const LEAD = 4;
const NUMERIC_LEFT = new Set(['Season', 'Team', 'Lg', 'Pos', 'Awards']);

function cellClass(flag) {
  if (!flag) return undefined;
  if (flag === 'g') return 'f-gold';
  if (flag === 'a') return 'f-ital';
  if (flag === 'bi') return 'f-bold f-ital';
  return flag === 'b' ? 'f-bold' : 'f-ital';
}

// Soft highlight in the team's color: stronger on the leading cells (Season through Lg), fainter on the stat cells.
// Single-team seasons and combined multi-team rows get the full tint (a combined row uses the color of its first team
// row); the team rows inside a multi-team group are softer. The career summary rows stay plain.
function leadStyle(r, lead) {
  let team;
  if (r.k === 'y' || r.k === 'x') team = r.v[2];
  else if (r.k === 'T') team = r.teamKey;
  else return undefined;
  const c = teamColor(String(team || '').split(' ')[0]);
  if (!c) return undefined;
  const pct = r.k === 'x' ? (lead ? 16 : 6) : (lead ? 28 : 10);
  return { background: `color-mix(in srgb, ${c} ${pct}%, transparent)` };
}

// Insert a "Did Not Play" row for every missing season between a player's first and last season in this table.
function withGaps(rows) {
  const out = [];
  let last = null;
  rows.forEach((r) => {
    if ((r.k === 'y' || r.k === 'T') && typeof r.v[0] === 'number') {
      if (last !== null) for (let y = last + 1; y < r.v[0]; y++) out.push({ k: 'dnp', year: y });
      last = r.v[0];
    }
    if (r.k === 'm' && out.length && out[out.length - 1].k === 'c') out.push({ k: 'spacer' });
    out.push(r);
  });
  // Mark each combined multi-team row ("2 Tms") and the team rows that follow it as one group.
  for (let i = 0; i < out.length; i++) {
    if (out[i].k !== 'T') continue;
    let j = i + 1;
    while (out[j] && out[j].k === 'x') j++;
    if (j === i + 1) continue;
    out[i] = { ...out[i], grp: 'first', teamKey: out[i + 1].v[2] };
    for (let k = i + 1; k < j; k++) out[k] = { ...out[k], grp: k === j - 1 ? 'last' : 'mid' };
    i = j - 1;
  }
  return out;
}

export default function StatTable({ kind, cols, rows, showWar }) {
  const box = useRef(null);
  const [more, setMore] = useState({ left: false, right: false });
  // Show an arrow at an edge while there is more table to scroll to on that side.
  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const update = () => setMore((m) => {
      const left = el.scrollLeft > 4, right = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
      return m.left === left && m.right === right ? m : { left, right };
    });
    update();
    el.addEventListener('scroll', update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el); if (el.firstElementChild) ro.observe(el.firstElementChild);
    return () => { el.removeEventListener('scroll', update); ro.disconnect(); };
  }, [rows, cols, showWar]);
  const nudge = (dir) => box.current?.scrollBy({ left: dir * Math.round(box.current.clientWidth * 0.7), behavior: 'smooth' });
  const visible = cols.map((c, i) => i).filter((i) => showWar || cols[i] !== 'WAR');
  return (
    <section className="table-block">
      <h2 className="table-title">{kind === 'bat' ? 'Regular Season Batting' : 'Regular Season Pitching'}</h2>
      <div className="table-wrap">
      <div className="table-scroll" ref={box}>
        <table className="stats-table">
          <thead>
            <tr>
              {visible.map((i) => (
                <th key={i} title={TOOLTIPS[cols[i]] ? TOOLTIPS[cols[i]] + (APPROX_COLS.has(cols[i]) ? ' (approximate; see note below table)' : '') : undefined} className={[NUMERIC_LEFT.has(cols[i]) ? 'left' : '', cols[i] === 'Lg' ? 'lg-sep' : ''].filter(Boolean).join(' ')}>
                  {headerLabel(cols[i])}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {withGaps(rows).map((r, ri) => r.k === 'spacer' ? (
              <tr key={ri} className="row-spacer"><td colSpan={visible.length} /></tr>
            ) : r.k === 'dnp' ? (
              <tr key={ri} className="row-dnp">
                <td className="left">{r.year}</td>
                <td colSpan={visible.length - 1}>Did Not Play</td>
              </tr>
            ) : (
              <tr key={ri} className={`row-${r.k}${r.grp ? ` grp grp-${r.grp}` : ''}`}>
                {(r.k === 'c' || r.k === 'm') && (
                  <td colSpan={LEAD} className="left lg-sep" style={leadStyle(r, true)}>{r.v.slice(0, LEAD).find((x) => x) || ''}</td>
                )}
                {visible.filter((i) => !((r.k === 'c' || r.k === 'm') && i < LEAD)).map((i) => {
                  const col = cols[i];
                  const v = r.v[i];
                  return (
                    <td key={i} style={leadStyle(r, i < LEAD)} className={[NUMERIC_LEFT.has(col) ? 'left' : '', col === 'Lg' ? 'lg-sep' : '', cellClass(r.f && r.f[i])].filter(Boolean).join(' ')}>
                      {col === 'Season' && r.k === 'x' && r.grp ? `${r.grp === 'last' ? '└' : '├'} ` : ''}
                      {col === 'Awards' && v ? <Awards value={v} /> : col === 'Team' && r.k === 'T' ? String(v).replace(/^(\d+) Tms$/, '$1TM') : formatCell(col, v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {more.left && <div className="scroll-hint left"><button type="button" aria-label="Scroll table left" onClick={() => nudge(-1)}><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M15.5 5l-7 7 7 7" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg></button></div>}
      {more.right && <div className="scroll-hint right"><button type="button" aria-label="Scroll table right" onClick={() => nudge(1)}><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M8.5 5l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg></button></div>}
      </div>
      <Legend tables={[rows]} />
      {visible.some((i) => APPROX_COLS.has(cols[i])) && (
        <p className="table-note muted small">* OPS+ and ERA+ are calculated here with approximate park factors, so they may differ slightly (typically 1–4 points) from Baseball-Reference.</p>
      )}
    </section>
  );
}

// Only lists the notes that apply to the tables being shown.
export function Legend({ tables }) {
  const rows = tables.flat();
  const flags = (rs) => rs.flatMap((r) => Object.values(r.f || {}));
  const season = flags(rows.filter((r) => r.k !== 'c' && r.k !== 'm'));
  const career = flags(rows.filter((r) => r.k === 'c'));
  const notes = [
    season.some((f) => f.includes('b')) && <li key="b"><b>Bold</b> season totals indicate player led league.</li>,
    season.some((f) => f.includes('i')) && <li key="i"><i>Italic</i> season totals indicate player led all major leagues.</li>,
    career.includes('a') && <li key="a"><i>Italic</i> career totals indicate player is active leader.</li>,
    career.includes('g') && <li key="g"><span className="f-gold">Gold</span> career totals indicate an all-time career record.</li>,
  ].filter(Boolean);
  if (!notes.length) return null;
  return <ul className="legend">{notes}</ul>;
}