import React, { useEffect, useState } from 'react';

// MLB's public headshot CDN. Falls back to initials if there is no ID or the image fails to load.
const url = (id, size) =>
  `https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_${size * 2},q_auto:best/v1/people/${id}/headshot/67/current`;

export default function Avatar({ mlbam, name, size = 44 }) {
  const [bad, setBad] = useState(!mlbam);
  useEffect(() => setBad(!mlbam), [mlbam]);
  const initials = name.split(' ').map((w) => w[0]).slice(0, 2).join('');
  const style = { width: size, height: size };
  if (bad) return <span className="avatar avatar-fallback" style={style} aria-hidden="true">{initials}</span>;
  return <img className="avatar" style={style} src={url(mlbam, size)} alt="" loading="lazy" onError={() => setBad(true)} />;
}
