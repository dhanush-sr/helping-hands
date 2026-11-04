import { useCallback, useEffect, useState } from 'react'
import { cancelShift, getAttendance, listManagedShifts, saveAttendance } from './api.js'
import ShiftForm from './ShiftForm.jsx'

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
      <p role="status">{message}</p>
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
      {rows?.length === 0 && <p>No confirmed volunteers.</p>}
      {rows?.map((row) => (
        <AttendanceEntry key={row.signup_id} row={row} shiftId={shiftId} onSaved={onSaved} />
      ))}
    </div>
  )
}

export default function ManagerShifts({ onChanged }) {
  const [shifts, setShifts] = useState([])
  const [editing, setEditing] = useState(null)
  const [attendance, setAttendance] = useState(null)
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

  return (
    <>
      <ShiftForm onSaved={saved} />
      <section className="card">
        <h2>Manage your shifts</h2>
        <p className="error" role="alert">{error}</p>
        <ul className="shift-list">
          {shifts.map((shift) => {
            const id = shift.shiftId
            const started = Date.parse(`${shift.date}T${shift.startTime}:00+05:30`) <= Date.now()
            const editable = !started && ['OPEN', 'FILLED'].includes(shift.status)
            return (
              <li className="shift" key={id}>
                <strong>{shift.task}</strong>
                <div>{shift.store} · {shift.date}, {shift.startTime}–{shift.endTime} · {shift.status}</div>
                {editable && <>
                  <button type="button" onClick={() => setEditing(id)}>Edit</button>
                  <button type="button" className="secondary"
                    onClick={() => setCancelId(id)}>Cancel shift</button>
                </>}
                {editable && cancelId === id && <div>
                  <p>Cancel this shift and notify its volunteers?</p>
                  <button type="button" disabled={busy} onClick={() => cancel(id)}>Confirm cancellation</button>
                  <button type="button" disabled={busy} onClick={() => setCancelId(null)}>Keep shift</button>
                </div>}
                {editable && editing === id && <ShiftForm key={id} shift={shift}
                  onSaved={() => { setEditing(null); saved() }} onDismiss={() => setEditing(null)} />}
                {started && shift.status !== 'CANCELLED' && <button type="button"
                  onClick={() => setAttendance(attendance === id ? null : id)}>
                  {attendance === id ? 'Hide attendance' : 'Attendance'}
                </button>}
                {attendance === id && <AttendanceRoster shiftId={id} onSaved={load} />}
              </li>
            )
          })}
        </ul>
      </section>
    </>
  )
}
