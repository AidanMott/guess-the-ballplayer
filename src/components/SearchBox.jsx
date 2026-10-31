import React, { useMemo, useRef, useState } from 'react';
import Avatar from './Avatar.jsx';
import { search } from '../lib/search.js';

export default function SearchBox({ players, norm, guessed, onGuess, disabled }) {
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const results = useMemo(() => search(players, norm, q, 10), [players, norm, q]);

  const pick = (p) => {
    if (!p || guessed.has(p.i)) return;
    onGuess(p);
    setQ('');
    setActive(0);
    inputRef.current?.focus();
  };

  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); pick(results[active]); }
    else if (e.key === 'Escape') setQ('');
  };

  return (
    <div className="search">
      <label htmlFor="guess-input" className="sr-only">Search for a player</label>
      <input
        id="guess-input" ref={inputRef} type="text" autoComplete="off" spellCheck="false"
        placeholder="Who is this player? Start typing a name…"
        value={q} disabled={disabled}
        onChange={(e) => { setQ(e.target.value); setActive(0); }}
        onKeyDown={onKey}
        role="combobox" aria-expanded={results.length > 0} aria-controls="guess-results"
      />
      {q.trim() && (
        <ul id="guess-results" className="results" role="listbox">
          {results.length === 0 && <li className="no-results">No players found</li>}
          {results.map((p, i) => {
            const done = guessed.has(p.i);
            return (
              <li key={p.i} role="option" aria-selected={i === active} aria-disabled={done}
                  className={`result${i === active ? ' active' : ''}${done ? ' done' : ''}`}
                  onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(p); }}>
                <Avatar mlbam={p.m} name={p.n} size={44} />
                <span className="result-text">
                  <span className="result-name">{p.n}</span>
                  <span className="result-meta">{p.pos}{done ? ' · already guessed' : ''}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
