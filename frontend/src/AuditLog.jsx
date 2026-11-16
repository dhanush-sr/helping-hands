import { useCallback, useEffect, useState } from 'react'
import { getAuditHistory, listUsers } from './api.js'
import { EmptyNote } from './ui.jsx'

const NO_FILTERS = { actor_id: '', action: '', since: '', until: '' }

// The admin's audit history (HH-33): who changed what, filtered by person, action or date.
function AuditLog() {
  const [filters, setFilters] = useState(NO_FILTERS)
  const [page, setPage] = useState(null)
  const [people, setPeople] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    listUsers()
      .then(setPeople)
      .catch((err) => setError(err.message))
  }, [])

  const load = useCallback(() => {
    getAuditHistory(filters)
      .then((data) => {
        setPage(data)
        setError('')
      })
      .catch((err) => setError(err.message))
  }, [filters])

  useEffect(load, [load])

  function set(name) {
    return {
      id: `audit-${name}`,
      value: filters[name],
      onChange: (event) => setFilters({ ...filters, [name]: event.target.value }),
    }
  }

  return (
    <section className="card">
      <h2 className="sr-only">Audit history</h2>

      <div className="filters">
        <div>
          <label htmlFor="audit-actor_id">Who</label>
          <select {...set('actor_id')}>
            <option value="">Anyone</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="audit-action">Action</label>
          <select {...set('action')}>
            <option value="">Any</option>
            {(page?.actions ?? []).map((action) => (
              <option key={action} value={action}>
                {action.replaceAll('_', ' ').toLowerCase()}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="audit-since">From</label>
          <input type="date" {...set('since')} />
        </div>
        <div>
          <label htmlFor="audit-until">To</label>
          <input type="date" {...set('until')} />
        </div>
        <button type="button" className="quiet" onClick={() => setFilters(NO_FILTERS)}>
          Clear filters
        </button>
      </div>

      <p className="error" role="alert">
        {error}
      </p>
      {page && page.events.length === 0 && !error && (
        <EmptyNote title="Nothing recorded for these filters">Clear a filter to see more of the history.</EmptyNote>
      )}

      <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Who</th>
            <th scope="col">Did what</th>
            <th scope="col">To</th>
          </tr>
        </thead>
        <tbody>
          {(page?.events ?? []).map((event) => (
            <tr key={event.id}>
              <td>{new Date(event.created_at).toLocaleString()}</td>
              <td>{event.actor}</td>
              <td>
                {event.action.replaceAll('_', ' ').toLowerCase()}
                <div className="muted">{event.detail}</div>
              </td>
              <td>
                {event.entity_type.toLowerCase()} {event.target_id}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </section>
  )
}

export default AuditLog
