import { useCallback, useEffect, useState } from 'react'
import {
  cancelShift,
  decideSignUp,
  getAttendance,
  getShiftSignUps,
  listManagedShifts,
  saveAttendance,
} from './api.js'
import ShiftForm from './ShiftForm.jsx'
import { EmptyNote, StatusStamp } from './ui.jsx'

function AttendanceEntry({ row, shiftId, onSaved }) {
  const [status, setStatus] = useState(row.status ?? 'ATTENDED')
  const [hours, setHours] = useState(row.hours_worked ?? '')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const saved = await saveAttendance(shiftId, row.signup_id, {
        status, hours_worked: status === 'NO_SHOW' ? 0 : Number(hours),
      })
      setHours(saved.hours_worked)
      setMessage('Saved.')
      onSaved()
    } catch (err) {
      setMessage(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <strong>{row.volunteer}</strong>
      <label>Attendance
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="ATTENDED">Attended</option>
          <option value="NO_SHOW">No-show</option>
        </select>
      </label>
      {status === 'ATTENDED' && <label>Hours worked
        <input type="number" min={0} step="any" required value={hours}
          onChange={(event) => setHours(event.target.value)} />
      </label>}
      <button disabled={busy}>Save attendance</button>
      <p role="status" className="muted">{message}</p>
    </form>
  )
}

function AttendanceRoster({ shiftId, onSaved }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    getAttendance(shiftId).then(setRows).catch((err) => setError(err.message))
  }, [shiftId])

  return (
    <div>
      <p className="error" role="alert">{error}</p>
      {rows?.length === 0 && <p className="muted">No confirmed volunteers on this shift.</p>}
      {rows?.map((row) => (
        <AttendanceEntry key={row.signup_id} row={row} shiftId={shiftId} onSaved={onSaved} />
      ))}
    </div>
  )
}


// Pending requests for one shift, with the manager's decision on each (HH-24).
function SignUpRequests({ shiftId, onDecided }) {
  const [data, setData] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    getShiftSignUps(shiftId)
      .then(setData)
      .catch((err) => setError(err.message))
  }, [shiftId])

  useEffect(load, [load])

  async function decide(signUpId, decision) {
    setBusyId(signUpId)
    setError('')
    try {
      await decideSignUp(signUpId, decision)
      load()
      onDecided()
    } catch (err) {
      setError(err.message)
      load()
    } finally {
      setBusyId(null)
    }
  }

  if (!data) return <p>{error || 'Loading requests…'}</p>

  const pending = data.signUps.filter((s) => s.status === 'REQUESTED')
  const decided = data.signUps.filter((s) => s.status !== 'REQUESTED')

  return (
    <div className="subpanel">
      <p className="error" role="alert">{error}</p>
      <p className="muted">
        {data.freeSlots} of {data.slotsNeeded} slots free
        {data.freeSlots === 0 && ' · this shift is full'}
      </p>
      {pending.length === 0 && <p className="muted">No one is waiting for a decision.</p>}
      <ul className="plain-list">
        {pending.map((signUp) => (
          <li key={signUp.signUpId} className="request">
            <span>{signUp.volunteer}</span>
            <span className="button-row">
              <button type="button" className="primary small"
                disabled={busyId === signUp.signUpId || data.freeSlots === 0}
                onClick={() => decide(signUp.signUpId, 'APPROVE')}>Approve</button>
              <button type="button" className="small" disabled={busyId === signUp.signUpId}
                onClick={() => decide(signUp.signUpId, 'DECLINE')}>Decline</button>
            </span>
          </li>
        ))}
        {decided.map((signUp) => (
          <li key={signUp.signUpId} className="request">
            <span>{signUp.volunteer}</span>
            <StatusStamp status={signUp.status} />
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function ManagerShifts({ onChanged }) {
  const [shifts, setShifts] = useState([])
  const [editing, setEditing] = useState(null)
  const [attendance, setAttendance] = useState(null)
  const [requests, setRequests] = useState(null)
  const [cancelId, setCancelId] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(() => {
    listManagedShifts().then(setShifts).catch((err) => setError(err.message))
  }, [])

  useEffect(load, [load])

  function saved() {
    load()
    onChanged()
  }

  async function cancel(id) {
    setBusy(true)
    setError('')
    try {
      await cancelShift(id)
      setCancelId(null)
      setEditing(null)
      saved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const isStarted = (shift) => Date.parse(`${shift.date}T${shift.startTime}:00+05:30`) <= Date.now()
  const upcoming = shifts.filter((shift) => !isStarted(shift))
  const past = shifts.filter(isStarted)

  function row(shift) {
    const id = shift.shiftId
    const started = isStarted(shift)
    const live = shift.status !== 'CANCELLED'
    const editable = !started && ['OPEN', 'FILLED'].includes(shift.status)
    return (
      <li className="list-card" key={id}>
        <div className="list-card-head">
          <strong className="list-card-title">{shift.task}</strong>
          <StatusStamp status={shift.status} />
        </div>
        <div className="meta">
          {shift.store} · {shift.date}, {shift.startTime}–{shift.endTime}
        </div>
        <div className="button-row">
          {!started && live && (
            <button type="button" className="small" aria-expanded={requests === id}
              onClick={() => setRequests(requests === id ? null : id)}>
              {requests === id ? 'Hide sign-ups' : 'Sign-ups'}
            </button>
          )}
          {started && live && (
            <button type="button" className="small" aria-expanded={attendance === id}
              onClick={() => setAttendance(attendance === id ? null : id)}>
              {attendance === id ? 'Hide attendance' : 'Record attendance'}
            </button>
          )}
          {editable && (
            <button type="button" className="small quiet" onClick={() => setEditing(editing === id ? null : id)}>
              Edit
            </button>
          )}
          {editable && (
            <button type="button" className="small danger" onClick={() => setCancelId(id)}>
              Cancel shift
            </button>
          )}
        </div>
        {editable && cancelId === id && (
          <div className="confirm">
            <p>Cancel this shift and notify its volunteers?</p>
            <div className="button-row">
              <button type="button" className="danger small" disabled={busy} onClick={() => cancel(id)}>
                Yes, cancel it
              </button>
              <button type="button" className="small" disabled={busy} onClick={() => setCancelId(null)}>
                Keep shift
              </button>
            </div>
          </div>
        )}
        {editable && editing === id && <ShiftForm key={id} shift={shift}
          onSaved={() => { setEditing(null); saved() }} onDismiss={() => setEditing(null)} />}
        {requests === id && <SignUpRequests shiftId={id} onDecided={saved} />}
        {attendance === id && <AttendanceRoster shiftId={id} onSaved={load} />}
      </li>
    )
  }

  return (
    <>
      <p className="error" role="alert">{error}</p>
      <h2 className="section-title">Coming up <span className="count">{upcoming.length}</span></h2>
      {upcoming.length === 0 ? (
        <EmptyNote title="No upcoming shifts">Post a shift to ask volunteers for help.</EmptyNote>
      ) : (
        <ul className="card-list">{upcoming.map(row)}</ul>
      )}
      <h2 className="section-title">Started or finished <span className="count">{past.length}</span></h2>
      {past.length === 0 ? (
        <EmptyNote title="Nothing has started yet">Attendance is recorded here once a shift begins.</EmptyNote>
      ) : (
        <ul className="card-list">{past.map(row)}</ul>
      )}
    </>
  )
}
