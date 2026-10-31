import { useEffect, useState } from 'react'
import { createShift, listBusyPeriods, listStores } from './api.js'

const EMPTY = {
  busyPeriodId: '',
  date: '',
  startTime: '',
  endTime: '',
  task: '',
  slotsNeeded: 1,
  notes: '',
}

// Today in the browser's time zone, as YYYY-MM-DD for <input type="date" min>.
function today() {
  const now = new Date()
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset())
  return now.toISOString().slice(0, 10)
}

// Store managers post a help request (HH-15). Times are store time (IST).
function ShiftForm() {
  const [stores, setStores] = useState([])
  const [periods, setPeriods] = useState([])
  const [storeId, setStoreId] = useState('')
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState('')
  const [posted, setPosted] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    Promise.all([listStores(), listBusyPeriods()])
      .then(([storeList, periodList]) => {
        setStores(storeList)
        setPeriods(periodList)
        if (storeList.length === 1) setStoreId(String(storeList[0].id))
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoaded(true))
  }, [])

  function field(name) {
    return {
      id: `shift-${name}`,
      value: form[name],
      onChange: (event) => setForm({ ...form, [name]: event.target.value }),
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setPosted('')
    setBusy(true)
    try {
      const created = await createShift({
        storeId: Number(storeId),
        busyPeriodId: form.busyPeriodId ? Number(form.busyPeriodId) : null,
        date: form.date,
        startTime: form.startTime,
        endTime: form.endTime,
        task: form.task,
        slotsNeeded: Number(form.slotsNeeded),
        notes: form.notes || null,
      })
      setPosted(
        `Posted: ${form.task} on ${form.date}, ${form.startTime} to ${form.endTime} ` +
          `(${created.freeSlots} volunteers needed).`,
      )
      setForm(EMPTY)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!loaded) return <p>Loading your stores…</p>

  if (stores.length === 0 && !error) {
    return (
      <section className="card">
        <h2>Post a shift</h2>
        <p>You don&apos;t manage an active store yet. Ask an admin to assign you one.</p>
      </section>
    )
  }

  return (
    <form className="card inline-form" onSubmit={handleSubmit}>
      <h2>Post a shift</h2>

      <label htmlFor="shift-store">Store</label>
      <select
        id="shift-store"
        value={storeId}
        onChange={(event) => setStoreId(event.target.value)}
        required
      >
        <option value="">Choose a store</option>
        {stores.map((store) => (
          <option key={store.id} value={store.id}>
            {store.name}
          </option>
        ))}
      </select>

      <label htmlFor="shift-busyPeriodId">Busy period (optional)</label>
      <select {...field('busyPeriodId')}>
        <option value="">None</option>
        {periods.map((period) => (
          <option key={period.id} value={period.id}>
            {period.name} ({period.start_date} to {period.end_date})
          </option>
        ))}
      </select>

      <label htmlFor="shift-date">Date</label>
      <input type="date" min={today()} required {...field('date')} />

      <label htmlFor="shift-startTime">Start time</label>
      <input type="time" required {...field('startTime')} />

      <label htmlFor="shift-endTime">End time</label>
      <input type="time" required {...field('endTime')} />

      <label htmlFor="shift-task">Task</label>
      <input placeholder="e.g. Billing counter" maxLength={120} required {...field('task')} />

      <label htmlFor="shift-slotsNeeded">Volunteers needed</label>
      <input type="number" min={1} max={100} required {...field('slotsNeeded')} />

      <label htmlFor="shift-notes">Notes (optional)</label>
      <textarea rows={2} maxLength={1000} {...field('notes')} />

      <p className="error" role="alert">
        {error}
      </p>
      <p className="ok" aria-live="polite">
        {posted}
      </p>

      <button type="submit" disabled={busy}>
        {busy ? 'Posting…' : 'Post shift'}
      </button>
    </form>
  )
}

export default ShiftForm
