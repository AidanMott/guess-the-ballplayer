import React, { useMemo } from 'react';
import { eligible, HITTER_POSITIONS, defaultFilters } from '../lib/filters.js';
import { teamColor, textOn } from '../lib/teamColors.js';

const DIVISIONS = [
  ['AL', 'E', 'AL East'], ['AL', 'C', 'AL Central'], ['AL', 'W', 'AL West'],
  ['NL', 'E', 'NL East'], ['NL', 'C', 'NL Central'], ['NL', 'W', 'NL West'],
];

export default function Filters({ meta, players, filters, setFilters, onStart, startLabel }) {
  const set = (k, v) => setFilters({ ...filters, [k]: v });
  const count = useMemo(() => eligible(players, filters).length, [players, filters]);
  const sel = new Set(filters.teams);
  const toggle = (id) => {
    const n = new Set(sel);
    n.has(id) ? n.delete(id) : n.add(id);
    set('teams', [...n]);
  };
  const toggleMany = (ids) => {
    const n = new Set(sel);
    const all = ids.every((id) => n.has(id));
    ids.forEach((id) => (all ? n.delete(id) : n.add(id)));
    set('teams', [...n]);
  };
  const posSel = new Set(filters.positions || []);
  const togglePos = (x) => {
    const n = new Set(posSel);
    n.has(x) ? n.delete(x) : n.add(x);
    set('positions', [...n]);
  };
  const active = meta.franchises.filter((f) => f.active).sort((a, b) => a.name.localeCompare(b.name));
  const defunct = meta.franchises.filter((f) => !f.active).sort((a, b) => a.name.localeCompare(b.name));
  // A selected team lights up in its own color (teams without one fall back to the default highlight).
  const chip = (f) => {
    const on = sel.has(f.id);
    const col = on ? teamColor(f.id) : null;
    return (
      <label key={f.id} className={`chip${on ? ' on' : ''}${col ? ' team-on' : ''}`}
             style={col ? { background: col, borderColor: col, color: textOn(col) } : undefined}>
        <input type="checkbox" checked={on} onChange={() => toggle(f.id)} />
        {f.name}
      </label>
    );
  };

  return (
    <section className="panel filters" aria-label="Player filters">
      <div className="filters-head">
        <div>
          <h2>Choose your player pool</h2>
          <p className="muted small">Changes apply the next time you pick a player.</p>
        </div>
        <div className="row">
          <button type="button" className="ghost" onClick={() => setFilters(defaultFilters(meta))}>Reset filters</button>
          <button className="primary" disabled={!count} onClick={onStart}>{startLabel}</button>
        </div>
      </div>
      <div className="grid">
        <fieldset>
          <legend>Played in any year between</legend>
          <div className="row">
            <input type="number" aria-label="From year" min={meta.minYear} max={meta.lastSeason} value={filters.yearFrom}
                   onChange={(e) => set('yearFrom', e.target.value)} />
            <span>and</span>
            <input type="number" aria-label="To year" min={meta.minYear} max={meta.lastSeason} value={filters.yearTo}
                   onChange={(e) => set('yearTo', e.target.value)} />
          </div>
        </fieldset>
        <fieldset>
          <legend>Player type</legend>
          <div className="row seg">
            {[['both', 'Hitters & pitchers'], ['bat', 'Hitters'], ['pit', 'Pitchers']].map(([v, l]) => (
              <label key={v} className={filters.type === v ? 'on' : ''}>
                <input type="radio" name="ptype" checked={filters.type === v} onChange={() => set('type', v)} />{l}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>Career minimums</legend>
          <div className="row mins">
            {filters.type !== 'pit' && (
              <label>Plate appearances <input type="number" min="0" step="100" value={filters.minPA} onChange={(e) => set('minPA', e.target.value)} /></label>
            )}
            {filters.type !== 'bat' && (
              <label>Innings pitched <input type="number" min="0" step="50" value={filters.minIP} onChange={(e) => set('minIP', e.target.value)} /></label>
            )}
            {filters.type !== 'bat' && (
              <label>Games pitched <input type="number" min="0" step="50" value={filters.minG} onChange={(e) => set('minG', e.target.value)} /></label>
            )}
          </div>
        </fieldset>
        {filters.type !== 'pit' && (
          <fieldset>
            <legend>Position (most-played in at least one season)</legend>
            <div className="chips positions">
              {[...HITTER_POSITIONS, ...(filters.type === 'both' ? ['P'] : [])].map((x) => (
                <label key={x} className={`chip${posSel.has(x) ? ' on' : ''}`}>
                  <input type="checkbox" checked={posSel.has(x)} onChange={() => togglePos(x)} />{x}
                </label>
              ))}
              {posSel.size > 0 && <button type="button" className="link" onClick={() => set('positions', [])}>Clear</button>}
            </div>
          </fieldset>
        )}
      </div>

      <fieldset className="teams">
        <legend>Teams {sel.size ? `(${sel.size} selected)` : '(all teams)'}</legend>
        <div className="row actions">
          <div className="row seg" role="radiogroup" aria-label="Team match rule">
            {[['or', 'Played for any of these'], ['and', 'Played for all of these']].map(([v, l]) => (
              <label key={v} className={filters.teamMode === v ? 'on' : ''}>
                <input type="radio" name="teammode" checked={filters.teamMode === v} onChange={() => set('teamMode', v)} />{l}
              </label>
            ))}
          </div>
          <button type="button" className="link" onClick={() => set('teams', [])}>Clear</button>
        </div>
        <div className="divisions">
          {DIVISIONS.map(([lg, d, label]) => {
            const fs = active.filter((f) => f.lg === lg && f.div === d);
            return (
              <div key={label} className="division">
                <button type="button" className="division-title" title={`Select or clear all ${label} teams`}
                        onClick={() => toggleMany(fs.map((f) => f.id))}>{label}</button>
                {fs.map(chip)}
              </div>
            );
          })}
        </div>
        <details>
          <summary>Historical franchises</summary>
          <div className="chips">{defunct.map(chip)}</div>
        </details>
      </fieldset>

      <div className="start-row">
        <span className={count ? 'muted' : 'warn'}>
          {count ? `${count.toLocaleString()} players match` : 'No players match these filters — loosen them to continue.'}
        </span>
      </div>
    </section>
  );
}