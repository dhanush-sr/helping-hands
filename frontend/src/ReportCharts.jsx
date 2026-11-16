// At-a-glance summaries above each report table (HH-32). Plain HTML/CSS marks, no chart
// library: one violet data hue for amounts, the design's red only for no-shows (a state).
// Every figure is also printed as text and stays in the table below, so nothing is colour-only.

const sum = (rows, key) => rows.reduce((total, row) => total + Number(row[key] || 0), 0)
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0)
const fmt = (n) => Number(n.toFixed(1)).toLocaleString()

function Stats({ items }) {
  return (
    <div className="stats-strip">
      {items.map(({ label, value, note, meter }) => (
        <div key={label} className="stats-item">
          <span className="stat-number">{value}</span>
          <span className="label">{label}</span>
          {meter !== undefined && <Meter value={meter} label={label} />}
          {note && <span className="muted stats-note">{note}</span>}
        </div>
      ))}
    </div>
  )
}

// A single ratio against its limit: track plus fill, 0..1.
function Meter({ value, label }) {
  const share = Math.max(0, Math.min(1, value))
  return (
    <span className="meter" role="img" aria-label={`${label}: ${Math.round(share * 100)}%`}>
      <span style={{ width: `${share * 100}%` }} />
    </span>
  )
}

function Coverage({ rows }) {
  const live = rows.filter((row) => row.status !== 'CANCELLED')
  const needed = sum(live, 'slots_needed')
  const filled = sum(live, 'confirmed')
  const short = live.filter((row) => row.open_slots > 0)
  // Only shifts still ahead can be helped; past gaps stay in the totals and the table.
  const today = new Date().toLocaleDateString('en-CA') // YYYY-MM-DD, local
  const upcomingShort = short.filter((row) => row.date >= today)

  // One store in scope (a manager): break it down by day instead.
  const byStore = new Set(live.map((row) => row.store)).size > 1
  const groups = new Map()
  for (const row of live) {
    const key = byStore ? row.store : row.date
    const group = groups.get(key) ?? { key, needed: 0, filled: 0 }
    group.needed += row.slots_needed
    group.filled += row.confirmed
    groups.set(key, group)
  }
  // Stores: worst-covered first, that is where help is needed. Days: in date order.
  const ranked = [...groups.values()].sort((a, b) => byStore
    ? a.filled / a.needed - b.filled / b.needed || a.key.localeCompare(b.key)
    : a.key.localeCompare(b.key))

  return (
    <>
      <Stats items={[
        { label: 'Slots filled', value: `${pct(filled, needed)}%`, meter: needed ? filled / needed : 0,
          note: `${filled} of ${needed} volunteer slots confirmed` },
        { label: 'Shifts short of volunteers', value: short.length, note: `of ${live.length} shifts in this range` },
        { label: 'Volunteers still needed', value: sum(upcomingShort, 'open_slots'),
          note: `for ${upcomingShort.length} upcoming shifts` },
      ]} />

      <div className="report-panels">
        <section className="card">
          <h3 className="section-title">Coverage by {byStore ? 'store' : 'day'}</h3>
          <ul className="bar-list">
            {ranked.map((group) => (
              <li key={group.key} title={`${group.key}: ${group.filled} of ${group.needed} slots filled`}>
                <span className="bar-label">{group.key}</span>
                <Meter value={group.filled / group.needed} label={group.key} />
                <span className="bar-value">{group.filled} / {group.needed}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <h3 className="section-title">Needs volunteers first <span className="count">{upcomingShort.length}</span></h3>
          {upcomingShort.length === 0 ? (
            <p className="muted">No upcoming shift is short of volunteers.</p>
          ) : (
            <ul className="gap-list">
              {upcomingShort.slice(0, 6).map((row) => (
                <li key={row.shift_id}>
                  <div>
                    <strong>{row.task}</strong>
                    <div className="muted">{row.store} · {row.date}, {row.start_time}–{row.end_time}</div>
                  </div>
                  <span className="need">{row.open_slots} more</span>
                </li>
              ))}
              {upcomingShort.length > 6 && (
                <li className="muted">and {upcomingShort.length - 6} more in the table below</li>
              )}
            </ul>
          )}
        </section>
      </div>
    </>
  )
}

function Hours({ rows }) {
  const total = sum(rows, 'hours')
  const top = rows.slice(0, 10) // already sorted, most hours first
  const max = Math.max(...top.map((row) => row.hours), 1)
  return (
    <>
      <Stats items={[
        { label: 'Hours worked', value: fmt(total) },
        { label: 'Volunteers', value: rows.length },
        { label: 'Average per volunteer', value: fmt(rows.length ? total / rows.length : 0), note: 'hours' },
      ]} />
      <section className="card">
        <h3 className="section-title">
          Most hours {rows.length > 10 && <span className="count">top 10 of {rows.length}</span>}
        </h3>
        <ul className="bar-list">
          {top.map((row) => (
            <li key={row.volunteer_id} title={`${row.volunteer}: ${fmt(row.hours)} hours over ${row.shifts} shifts`}>
              <span className="bar-label">{row.volunteer}</span>
              <span className="bar-track"><span className="bar" style={{ width: `${(row.hours / max) * 100}%` }} /></span>
              <span className="bar-value">{fmt(row.hours)} h</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}

function NoShows({ rows }) {
  const missed = sum(rows, 'no_shows')
  const came = sum(rows, 'attended')
  return (
    <>
      <Stats items={[
        { label: 'No-shows', value: missed },
        { label: 'Volunteers with a no-show', value: rows.length },
        { label: 'Their turn-up rate', value: `${pct(came, came + missed)}%`,
          note: `${came} of ${came + missed} confirmed shifts attended` },
      ]} />
      <section className="card">
        <div className="section-head">
          <h3 className="section-title">Attended and missed, per volunteer</h3>
          <span className="legend">
            <span><i className="swatch attended" /> Attended</span>
            <span><i className="swatch missed" /> No-show</span>
          </span>
        </div>
        <ul className="bar-list">
          {rows.map((row) => {
            const all = row.attended + row.no_shows
            return (
              <li key={row.volunteer_id} title={`${row.volunteer}: ${row.attended} attended, ${row.no_shows} missed`}>
                <span className="bar-label">{row.volunteer}</span>
                <span className="split-bar" role="img"
                  aria-label={`${row.attended} attended, ${row.no_shows} missed`}>
                  {row.attended > 0 && <span className="attended" style={{ flexGrow: row.attended / all }} />}
                  {row.no_shows > 0 && <span className="missed" style={{ flexGrow: row.no_shows / all }} />}
                </span>
                <span className="bar-value">{row.no_shows} missed</span>
              </li>
            )
          })}
        </ul>
      </section>
    </>
  )
}

export default function ReportSummary({ tab, rows }) {
  if (tab === 'coverage') return <Coverage rows={rows} />
  if (tab === 'hours') return <Hours rows={rows} />
  if (tab === 'no-shows') return <NoShows rows={rows} />
  return null
}
