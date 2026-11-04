import { useCallback, useEffect, useState } from 'react'
import { cancelShift, listManagedShifts } from './api.js'
import ShiftForm from './ShiftForm.jsx'

export default function ManagerShifts({ onChanged }) {
  const [shifts, setShifts] = useState([])
  const [editing, setEditing] = useState(null)
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
              </li>
            )
          })}
        </ul>
      </section>
    </>
  )
}
