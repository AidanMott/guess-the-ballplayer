import React from 'react';
import Avatar from './Avatar.jsx';

export default function GuessLog({ guesses }) {
  if (!guesses.length) return <p className="muted">No guesses yet.</p>;
  return (
    <ol className="guess-log" reversed>
      {[...guesses].reverse().map((g) => (
        <li key={g.p.i} className={g.correct ? 'correct' : 'wrong'}>
          <Avatar mlbam={g.p.m} name={g.p.n} size={32} />
          <span className="g-name">{g.p.n}</span>
          <span className="g-meta">{g.p.pos}</span>
          <span className="g-mark" aria-label={g.correct ? 'correct' : 'incorrect'}>{g.correct ? '✓' : '✗'}</span>
        </li>
      ))}
    </ol>
  );
}
