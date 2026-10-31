import { useCallback, useEffect, useState } from 'react'
import {
  createBusyPeriod,
  createStore,
  listBusyPeriods,
  listStoreManagers,
  listStores,
  updateStore,
} from './api.js'

// Admin pages for stores and busy periods (HH-13).
function AdminPanel() {
  return (
    <>
      <StoresAdmin />
      <BusyPeriodsAdmin />
    </>
  )
}

function StoresAdmin() {
  const [stores, setStores] = useState([])
  const [managers, setManagers] = useState([])
  const [form, setForm] = useState({ name: '', location: '', managerId: '' })
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    Promise.all([listStores(), listStoreManagers()])
      .then(([storeList, managerList]) => {
        setStores(storeList)
        setManagers(managerList)
      })
      .catch((err) => setMessage(err.message))
  }, [])

  useEffect(load, [load])

  async function run(action) {
    setMessage('')
    try {
      await action()
      load()
    } catch (err) {
      setMessage(err.message)
    }
  }

  function handleCreate(event) {
    event.preventDefault()
    run(async () => {
      await createStore({
        name: form.name,
        location: form.location,
        manager_id: form.managerId ? Number(form.managerId) : null,
      })
      setForm({ name: '', location: '', managerId: '' })
    })
  }

  return (
    <section className="card">
      <h2>Stores</h2>
      <p className="error" role="alert">
        {message}
      </p>

      <table>
        <thead>
          <tr>
            <th scope="col">Store</th>
            <th scope="col">Location</th>
            <th scope="col">Manager</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {stores.map((store) => (
            <tr key={store.id}>
              <td>{store.name}</td>
              <td>{store.location}</td>
              <td>
                <select
                  aria-label={`Manager of ${store.name}`}
                  value={store.manager?.id ?? ''}
                  onChange={(event) =>
                    run(() =>
                      updateStore(store.id, {
                        manager_id: event.target.value ? Number(event.target.value) : null,
                      }),
                    )
                  }
                >
                  <option value="">No manager</option>
                  {managers.map((manager) => (
                    <option key={manager.id} value={manager.id}>
                      {manager.full_name}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => run(() => updateStore(store.id, { is_active: !store.is_active }))}
                >
                  {store.is_active ? 'Deactivate' : 'Activate'}
                </button>{' '}
                {store.is_active ? 'Active' : 'Inactive'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <form className="inline-form" onSubmit={handleCreate}>
        <h3>Add a store</h3>
        <label htmlFor="store-name">Name</label>
        <input
          id="store-name"
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
          required
        />
        <label htmlFor="store-location">Location</label>
        <input
          id="store-location"
          value={form.location}
          onChange={(event) => setForm({ ...form, location: event.target.value })}
          required
        />
        <label htmlFor="store-manager">Manager</label>
        <select
          id="store-manager"
          value={form.managerId}
          onChange={(event) => setForm({ ...form, managerId: event.target.value })}
        >
          <option value="">No manager yet</option>
          {managers.map((manager) => (
            <option key={manager.id} value={manager.id}>
              {manager.full_name}
            </option>
          ))}
        </select>
        <button type="submit">Add store</button>
      </form>
    </section>
  )
}

function BusyPeriodsAdmin() {
  const [periods, setPeriods] = useState([])
  const [form, setForm] = useState({ name: '', startDate: '', endDate: '' })
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    listBusyPeriods()
      .then(setPeriods)
      .catch((err) => setMessage(err.message))
  }, [])

  useEffect(load, [load])

  async function handleCreate(event) {
    event.preventDefault()
    setMessage('')
    try {
      await createBusyPeriod({
        name: form.name,
        start_date: form.startDate,
        end_date: form.endDate,
      })
      setForm({ name: '', startDate: '', endDate: '' })
      load()
    } catch (err) {
      setMessage(err.message)
    }
  }

  return (
    <section className="card">
      <h2>Busy periods</h2>
      <p className="error" role="alert">
        {message}
      </p>

      <table>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">From</th>
            <th scope="col">To</th>
          </tr>
        </thead>
        <tbody>
          {periods.map((period) => (
            <tr key={period.id}>
              <td>{period.name}</td>
              <td>{period.start_date}</td>
              <td>{period.end_date}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <form className="inline-form" onSubmit={handleCreate}>
        <h3>Add a busy period</h3>
        <label htmlFor="period-name">Name</label>
        <input
          id="period-name"
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
          required
        />
        <label htmlFor="period-start">From</label>
        <input
          id="period-start"
          type="date"
          value={form.startDate}
          onChange={(event) => setForm({ ...form, startDate: event.target.value })}
          required
        />
        <label htmlFor="period-end">To</label>
        <input
          id="period-end"
          type="date"
          min={form.startDate || undefined}
          value={form.endDate}
          onChange={(event) => setForm({ ...form, endDate: event.target.value })}
          required
        />
        <button type="submit">Add busy period</button>
      </form>
    </section>
  )
}

export default AdminPanel
