import React, { useCallback, useEffect, useRef, useState } from 'react';
import { loadIndex, loadPlayer } from './lib/data.js';
import { eligible, loadSavedFilters, saveFilters } from './lib/filters.js';
import StatTable from './components/StatTable.jsx';
import SearchBox from './components/SearchBox.jsx';
import GuessLog from './components/GuessLog.jsx';
import Filters from './components/Filters.jsx';
import Summary from './components/Summary.jsx';

const TYPE_LABEL = { both: 'Hitters & pitchers', bat: 'Hitters', pit: 'Pitchers' };
const filterSummary = (f) =>
  [
    `${f.yearFrom}–${f.yearTo}`,
    TYPE_LABEL[f.type],
    f.notable ? 'notable' : null,
    f.winners ? 'award winners' : null,
    f.type !== 'pit' && f.positions.length ? f.positions.join('/') : null,
    f.teams.length ? `${f.teamMode === 'and' && f.teams.length > 1 ? 'all of ' : ''}${f.teams.length} team${f.teams.length > 1 ? 's' : ''}` : 'all teams',
  ].filter(Boolean).join(' · ');

export default function App() {
  const [data, setData] = useState(null);       // { meta, players, norm }
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const [phase, setPhase] = useState('loading'); // loading | playing | over | empty
  const [target, setTarget] = useState(null);    // index entry of the mystery player
  const [entry, setEntry] = useState(null);      // full tables for the mystery player
  const [guesses, setGuesses] = useState([]);
  const [result, setResult] = useState(null);    // won | gave_up
  const [confirmGiveUp, setConfirmGiveUp] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme === 'light' ? 'light' : 'dark');
  const [showRings, setShowRings] = useState(() => { try { return localStorage.getItem('rg.rings') !== 'off'; } catch { return true; } });
  const played = useRef(new Set());
  const booted = useRef(false);
  const request = useRef(0);
  const toolbar = useRef(null);

  useEffect(() => {
    loadIndex().then((d) => { setData(d); setFilters(loadSavedFilters(d.meta)); }).catch(setError);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('rg.theme', theme); } catch { /* ignore */ }
  }, [theme]);

  useEffect(() => {
    try { localStorage.setItem('rg.rings', showRings ? 'on' : 'off'); } catch { /* ignore */ }
  }, [showRings]);

  // Filters are remembered, so a refresh comes back with the same settings.
  useEffect(() => { if (filters) saveFilters(filters); }, [filters]);

  // Pick a random player from the current filters, never the one currently on screen.
  const start = useCallback(async () => {
    const pool = eligible(data.players, filters);
    if (!pool.length) { setPhase('empty'); setShowFilters(true); return; }
    const currentId = target ? target.i : null;
    let fresh = pool.filter((p) => p.i !== currentId && !played.current.has(p.i));
    if (!fresh.length) { played.current.clear(); fresh = pool.filter((p) => p.i !== currentId); }
    if (!fresh.length) fresh = pool; // the pool has only one player
    const pick = fresh[Math.floor(Math.random() * fresh.length)];
    played.current.add(pick.i);
    const mine = ++request.current;
    setShowFilters(false);
    setPhase('loading');
    toolbar.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    try {
      const e = await loadPlayer(data.meta, pick.i);
      if (mine !== request.current) return; // a newer pick superseded this one
      setTarget(pick); setEntry(e); setGuesses([]); setResult(null); setConfirmGiveUp(false);
      setPhase('playing');
    } catch (err) { setError(err); }
  }, [data, filters, target]);

  // Start a round as soon as the data is loaded.
  useEffect(() => {
    if (data && filters && !booted.current) { booted.current = true; start(); }
  }, [data, filters, start]);

  const guess = (p) => {
    const correct = p.i === target.i;
    setGuesses((g) => [...g, { p, correct }]);
    if (correct) { setResult('won'); setPhase('over'); }
  };
  const giveUp = () => { setResult('gave_up'); setPhase('over'); };

  // Keyboard shortcuts (they step aside whenever the person is typing in, or pressing, a control).
  //   result screen:  Enter / Space / Escape -> next player
  //   guessing:       Escape -> "Give up?", Escape again -> give up;  any letter/number -> jump to the guess box
  useEffect(() => {
    const onKey = (e) => {
      if (e.defaultPrevented || e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target;
      const tag = t && t.tagName;
      const typing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable);
      const onGuessBox = t && t.id === 'guess-input';
      const pressable = tag === 'BUTTON' || tag === 'A' || tag === 'SUMMARY';
      if (phase === 'over') {
        if (((e.key === 'Enter' || e.key === ' ') && !pressable || e.key === 'Escape') && !typing) { e.preventDefault(); start(); }
      } else if (phase === 'playing') {
        if (e.key === 'Escape') {
          if (typing && !onGuessBox) return;
          e.preventDefault();
          if (confirmGiveUp) giveUp(); else setConfirmGiveUp(true);
        } else if (e.key.length === 1 && onGuessBox && confirmGiveUp) {
          setConfirmGiveUp(false);   // typing a guess dismisses the "give up?" prompt
        } else if (e.key.length === 1 && e.key !== ' ' && !typing) {
          setConfirmGiveUp(false);
          document.getElementById('guess-input')?.focus();   // the key press then types into the box
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  if (error) return <main className="wrap"><p className="warn">Couldn’t load the player data: {String(error.message || error)}</p></main>;
  if (!data || !filters) return <main className="wrap"><p className="muted">Loading players…</p></main>;

  const { meta, players, norm } = data;
  const guessedIds = new Set(guesses.map((g) => g.p.i));
  const showTables = (phase === 'playing' || phase === 'over') && entry;

  return (
    <main className={`wrap${phase === 'playing' ? ' has-dock' : ''}`}>
      <header className="site-header">
        <div className="header-tools">
          <button className="ghost theme-toggle" aria-pressed={showRings} onClick={() => setShowRings((r) => !r)}
                  title="Show a ring next to the team in seasons it won the World Series">
            Rings: {showRings ? 'On' : 'Off'}
          </button>
          <button className="ghost theme-toggle" onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
                  aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
            {theme === 'dark' ? '☀ Light' : '☾ Dark'}
          </button>
        </div>
        <h1>Guess the Ballplayer</h1>
        <p className="muted">
          Identify the player from their career stat table.
        </p>
      </header>

      <div className="toolbar" ref={toolbar}>
        <button className={`filters-toggle${showFilters ? ' open' : ''}`} aria-expanded={showFilters} onClick={() => setShowFilters((o) => !o)}>
          <span className="ft-label">☰ Filters</span>
          <span className="ft-summary">{filterSummary(filters)}</span>
          <span className="ft-chevron" aria-hidden="true">{showFilters ? 'Hide ▴' : 'Show ▾'}</span>
        </button>
        <button className="primary" onClick={start} disabled={phase === 'loading'}>
          {phase === 'loading' ? 'Picking…' : 'Pick a new player'}
        </button>
      </div>

      {showFilters && (
        <Filters meta={meta} players={players} filters={filters} setFilters={setFilters} onStart={start}
                 startLabel="Pick a new player" />
      )}

      {phase === 'empty' && <p className="warn">No players match these filters. Loosen them to continue.</p>}

      {phase === 'over' && (
        <Summary target={target} entry={entry} meta={meta} result={result} guesses={guesses} onNext={start} />
      )}

      {showTables && (
        <>
          {entry.bat && <StatTable kind="bat" cols={meta.batCols} rows={entry.bat} showWar={meta.warLoaded} showRings={showRings} />}
          {entry.pit && <StatTable kind="pit" cols={meta.pitCols} rows={entry.pit} showWar={meta.warLoaded} showRings={showRings} />}
        </>
      )}

      {phase === 'playing' && (
        <div className="dock">
          {logOpen && <div className="dock-log"><GuessLog guesses={guesses} /></div>}
          <div className="dock-inner">
            <button className="ghost log-toggle" aria-expanded={logOpen} onClick={() => setLogOpen((o) => !o)}>
              Guesses ({guesses.length}) {logOpen ? '▾' : '▴'}
            </button>
            <SearchBox players={players} norm={norm} guessed={guessedIds} onGuess={guess} />
            {!confirmGiveUp
              ? <button className="ghost" onClick={() => setConfirmGiveUp(true)}>Give up</button>
              : <span className="confirm">Reveal the answer? <button className="danger" onClick={giveUp}>Yes, give up</button> <button className="ghost" onClick={() => setConfirmGiveUp(false)}>Keep playing</button></span>}
          </div>
        </div>
      )}

      <footer className="site-footer muted small">
        <p>Stat sheets are laid out like <b>Baseball-Reference.com</b> and built from the Lahman database through the {meta.lastSeason} season.</p>
        <p>Fan project, not affiliated with Baseball-Reference.com or MLB.</p>
        <p>Data: Lahman Baseball Database (CC BY-SA 3.0); player IDs: Chadwick Bureau Register; headshots: MLB.</p>
      </footer>
    </main>
  );
}