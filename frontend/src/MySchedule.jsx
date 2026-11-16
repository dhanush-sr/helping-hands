import { useCallback, useEffect, useState } from 'react'
import { getMySchedule, withdrawSignUp } from './api.js'
import { EmptyNote, StatusStamp } from './ui.jsx'

// A volunteer's own shifts (HH-26): what is coming up, what they can still drop, what they
// have already done, and how much of the week's limit they have used.
function MySchedule({ onChanged }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(() => {
    getMySchedule()
      .then(setData)
      .catch((err) => setError(err.message))
  }, [])

  useEffect(load, [load])

  async function withdraw(signUpId) {
    setBusyId(signUpId)
    setError('')
    try {
      await withdrawSignUp(signUpId)
      load()
      onChanged?.()
    } catch (err) {
      setError(err.message)
      load()
    } finally {
      setBusyId(null)
    }
  }

  if (!data) return <section className="card">{error || 'Loading your schedule…'}</section>

  const overLimit = data.hoursThisWeek > data.weeklyHourLimit

  return (
    <section className="card">
      <h2 className="sr-only">My schedule</h2>
      <p className="error" role="alert">
        {error}
      </p>
      <div className="stat">
        <span className={`stat-number${overLimit ? ' error' : ''}`}>
          {data.hoursThisWeek}<span className="muted"> / {data.weeklyHourLimit}</span>
        </span>
        <span className="label">Hours held this week{overLimit && ' · over the limit'}</span>
      </div>

      <h3 className="section-title">Coming up <span className="count">{data.upcoming.length}</span></h3>
      {data.upcoming.length === 0 && (
        <EmptyNote title="Nothing booked yet">Pick a shift under Find shifts and sign up.</EmptyNote>
      )}
      <ul className="shift-list">
        {data.upcoming.map((entry) => (
          <li className="shift" key={entry.signUpId}>
            <div className="shift-head">
              <strong>{entry.task}</strong>
              <StatusStamp status={entry.status} />
            </div>
            <div>{entry.store}</div>
            <div>
              {entry.date}, {entry.startTime} to {entry.endTime}
              <span className="muted"> · {entry.hours} hours</span>
            </div>
            {entry.canWithdraw ? (
              <button
                type="button"
                className="small"
                disabled={busyId === entry.signUpId}
                onClick={() => withdraw(entry.signUpId)}
              >
                {busyId === entry.signUpId ? 'Withdrawing…' : 'Withdraw'}
              </button>
            ) : (
              <span className="muted">Too close to the start to withdraw</span>
            )}
          </li>
        ))}
      </ul>

      <h3 className="section-title">Already done <span className="count">{data.past.length}</span></h3>
      {data.past.length === 0 && <EmptyNote title="No past shifts yet">Shifts you have worked will show here.</EmptyNote>}
      <ul className="shift-list">
        {data.past.map((entry) => (
          <li className="shift" key={entry.signUpId}>
            <div className="shift-head">
              <strong>{entry.task}</strong>
              <span className="stamp-with-note">
                {entry.attendance === 'ATTENDED' && <span className="muted">{entry.hoursWorked} h</span>}
                <StatusStamp status={entry.attendance ?? 'NOT_RECORDED'} />
              </span>
            </div>
            <div>
              {entry.store} · {entry.date}, {entry.startTime} to {entry.endTime}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default MySchedule
