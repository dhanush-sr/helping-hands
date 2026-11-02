import { useEffect, useState } from 'react'
import { listBusyPeriods, listShifts, signUpForShift } from './api.js'

const NO_FILTERS = { date: '', busyPeriodId: '', storeId: '', task: '' }

// Codes where the volunteer has, in effect, already asked; the button stays done.
const ALREADY_ASKED = new Set(['ALREADY_SIGNED_UP'])

// Browse and filter open shifts (HH-16). Laid out as stacked cards so it works on a phone.
// Volunteers get a Sign up button on each card (HH-17): browse, tap, done.
function ShiftList({ canSignUp = false }) {
  const [filters, setFilters] = useState(NO_FILTERS)
  const [shifts, setShifts] = useState([])
  const [stores, setStores] = useState([])
  const [periods, setPeriods] = useState([])
  const [state, setState] = useState('loading')
  const [error, setError] = useState('')
  // shiftId -> { state: 'sending' | 'requested' | 'refused', message }
  const [signUps, setSignUps] = useState({})

  // Filter choices: busy periods from the API, stores from the open shifts themselves
  // (volunteers can't list stores).
  useEffect(() => {
    Promise.all([listBusyPeriods(), listShifts({})])
      .then(([periodList, allShifts]) => {
        setPeriods(periodList)
        const byId = new Map(allShifts.map((shift) => [shift.storeId, shift.store]))
        setStores([...byId].map(([id, name]) => ({ id, name })).sort((a, b) =>
          a.name.localeCompare(b.name),
        ))
      })
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    // Wait a moment after typing in the task box before asking the API again.
    const timer = setTimeout(() => {
      listShifts(filters)
        .then((found) => {
          setShifts(found)
          setState('ready')
          setError('')
        })
        .catch((err) => {
          setError(err.message)
          setState('ready')
        })
    }, 250)
    return () => clearTimeout(timer)
  }, [filters])

  function set(name) {
    return {
      id: `filter-${name}`,
      value: filters[name],
      onChange: (event) => setFilters({ ...filters, [name]: event.target.value }),
    }
  }

  function mark(shiftId, value) {
    setSignUps((current) => ({ ...current, [shiftId]: value }))
  }

  async function handleSignUp(shift) {
    mark(shift.shiftId, { state: 'sending' })
    try {
      await signUpForShift(shift.shiftId)
      mark(shift.shiftId, {
        state: 'requested',
        message: 'Requested. The store manager will confirm it.',
      })
    } catch (err) {
      mark(shift.shiftId, {
        state: ALREADY_ASKED.has(err.code) ? 'requested' : 'refused',
        message: err.message,
      })
    }
  }

  return (
    <section className="card">
      <h2>Open shifts</h2>

      <div className="filters">
        <div>
          <label htmlFor="filter-date">Date</label>
          <input type="date" {...set('date')} />
        </div>
        <div>
          <label htmlFor="filter-busyPeriodId">Busy period</label>
          <select {...set('busyPeriodId')}>
            <option value="">Any</option>
            {periods.map((period) => (
              <option key={period.id} value={period.id}>
                {period.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="filter-storeId">Store</label>
          <select {...set('storeId')}>
            <option value="">Any</option>
            {stores.map((store) => (
              <option key={store.id} value={store.id}>
                {store.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="filter-task">Task</label>
          <input placeholder="e.g. billing" {...set('task')} />
        </div>
        <button type="button" className="secondary" onClick={() => setFilters(NO_FILTERS)}>
          Clear filters
        </button>
      </div>

      <p className="error" role="alert">
        {error}
      </p>
      {state === 'loading' && <p>Loading shifts…</p>}
      {state === 'ready' && shifts.length === 0 && !error && (
        <p>No open shifts match these filters.</p>
      )}

      <ul className="shift-list" aria-live="polite">
        {shifts.map((shift) => (
          <li key={shift.shiftId} className="shift">
            <div className="shift-head">
              <strong>{shift.task}</strong>
              <span className="slots">
                {shift.freeSlots} of {shift.slotsNeeded} {shift.slotsNeeded === 1 ? 'slot' : 'slots'}{' '}
                free
              </span>
            </div>
            <div>{shift.store}</div>
            <div>
              {shift.date}, {shift.startTime} to {shift.endTime}
              {shift.busyPeriod && <span className="muted"> · {shift.busyPeriod}</span>}
            </div>
            {canSignUp && (
              <SignUpAction
                shift={shift}
                signUp={signUps[shift.shiftId]}
                onSignUp={() => handleSignUp(shift)}
              />
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function SignUpAction({ shift, signUp, onSignUp }) {
  const state = signUp?.state
  const done = state === 'requested'
  return (
    <div className="signup">
      <button
        type="button"
        onClick={onSignUp}
        disabled={state === 'sending' || done}
        aria-label={`Sign up for ${shift.task} at ${shift.store}, ${shift.date} ${shift.startTime}`}
      >
        {state === 'sending' ? 'Signing up…' : done ? 'Requested' : 'Sign up'}
      </button>
      {signUp?.message && (
        <p className={done ? 'ok' : 'error'} role="status">
          {signUp.message}
        </p>
      )}
    </div>
  )
}

export default ShiftList
