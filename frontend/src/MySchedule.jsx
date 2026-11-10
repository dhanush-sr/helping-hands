import { useCallback, useEffect, useState } from 'react'
import { getMySchedule, withdrawSignUp } from './api.js'

const STATUS_LABEL = {
  REQUESTED: 'Waiting for the manager',
  CONFIRMED: 'Confirmed',
  DECLINED: 'Declined',
  WITHDRAWN: 'Withdrawn',
}

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
      <h2>My schedule</h2>
      <p className="error" role="alert">
        {error}
      </p>
      <p className={overLimit ? 'error' : ''}>
        {data.hoursThisWeek} of {data.weeklyHourLimit} hours held this week
        {overLimit && ' · over the limit'}
      </p>

      <h3>Coming up</h3>
      {data.upcoming.length === 0 && <p>Nothing booked yet.</p>}
      <ul className="shift-list">
        {data.upcoming.map((entry) => (
          <li className="shift" key={entry.signUpId}>
            <div className="shift-head">
              <strong>{entry.task}</strong>
              <span>{STATUS_LABEL[entry.status] ?? entry.status}</span>
            </div>
            <div>{entry.store}</div>
            <div>
              {entry.date}, {entry.startTime} to {entry.endTime}
              <span className="muted"> · {entry.hours} hours</span>
            </div>
            {entry.canWithdraw ? (
              <button
                type="button"
                className="secondary"
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

      <h3>Already done</h3>
      {data.past.length === 0 && <p>No past shifts yet.</p>}
      <ul className="shift-list">
        {data.past.map((entry) => (
          <li className="shift" key={entry.signUpId}>
            <div className="shift-head">
              <strong>{entry.task}</strong>
              <span>
                {entry.attendance === 'ATTENDED' && `Attended · ${entry.hoursWorked} hours`}
                {entry.attendance === 'NO_SHOW' && 'Marked no-show'}
                {!entry.attendance && 'Not recorded yet'}
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
