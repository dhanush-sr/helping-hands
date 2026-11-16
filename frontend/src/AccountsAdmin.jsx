import { useEffect, useState } from 'react'
import { createUser, getRules, listUsers, saveRules, updateUser } from './api.js'
import { StatusStamp } from './ui.jsx'

const ROLES = { VOLUNTEER: 'Volunteer', STORE_MANAGER: 'Store manager', ADMIN: 'Admin' }
const EMPTY = { full_name: '', email: '', password: '', role: 'VOLUNTEER' }
const RULES = {
  weekly_hour_limit: 'Weekly hour limit',
  min_notice_hours: 'Minimum notice (hours)',
  withdrawal_cutoff_hours: 'Withdrawal cutoff (hours)',
}

function RoleOptions() {
  return Object.entries(ROLES).map(([role, label]) => (
    <option key={role} value={role}>{label}</option>
  ))
}

// view: 'users' (the accounts list and the add form) or 'rules' (volunteering rules).
export default function AccountsAdmin({ view = 'users', currentUserId }) {
  const [users, setUsers] = useState([])
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState(false)
  const [rules, setRules] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listUsers().then(setUsers).catch((err) => setError(err.message))
    getRules().then(setRules).catch((err) => setError(err.message))
  }, [])

  async function run(action) {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function change(user, fields) {
    run(async () => {
      const updated = await updateUser(user.id, {
        role: user.role, is_active: user.is_active, ...fields,
      })
      setUsers((rows) => rows.map((row) => row.id === updated.id ? updated : row))
    })
  }

  function field(name) {
    return {
      value: form[name],
      onChange: (event) => setForm({ ...form, [name]: event.target.value }),
    }
  }

  const errorLine = <p className="error" role="alert">{error}</p>

  if (view === 'rules') {
    return (
      <section className="card narrow">
        <h2 className="sr-only">Volunteering rules</h2>
        {errorLine}
        {!rules && !error && <p className="muted">Loading the rules…</p>}
        {rules && (
          <form className="inline-form" onSubmit={(event) => {
            event.preventDefault()
            run(async () => setRules(await saveRules(
              Object.fromEntries(Object.entries(rules).map(([key, value]) => [key, Number(value)])),
            )))
          }}>
            {Object.entries(RULES).map(([key, label]) => (
              <label key={key}>{label}
                <input type="number" min={1} max={2147483647} required value={rules[key]}
                  onChange={(event) => setRules({ ...rules, [key]: event.target.value })} />
              </label>
            ))}
            <button disabled={busy}>Save rules</button>
          </form>
        )}
      </section>
    )
  }

  const needle = query.trim().toLowerCase()
  const shown = needle
    ? users.filter((user) => `${user.full_name} ${user.email}`.toLowerCase().includes(needle))
    : users

  return (
    <>
      {adding && (
        <section className="card narrow">
          <h2 className="section-title">Add a user</h2>
          <form className="inline-form" onSubmit={(event) => {
            event.preventDefault()
            run(async () => {
              const created = await createUser(form)
              setUsers((rows) => [...rows, created])
              setForm(EMPTY)
              setAdding(false)
            })
          }}>
            <label>Full name <input required maxLength={120} {...field('full_name')} /></label>
            <label>Email <input type="email" required maxLength={255} {...field('email')} /></label>
            <label>Temporary password
              <input type="password" autoComplete="new-password" required minLength={8}
                maxLength={72} {...field('password')} />
            </label>
            <label>Role <select {...field('role')}><RoleOptions /></select></label>
            <div className="button-row">
              <button disabled={busy}>Add user</button>
              <button type="button" className="quiet" onClick={() => setAdding(false)}>Cancel</button>
            </div>
          </form>
        </section>
      )}
      <section className="card">
        <div className="section-head">
          <h2 className="section-title">People <span className="count">{shown.length}</span></h2>
          {!adding && (
            <button type="button" className="primary" onClick={() => setAdding(true)}>Add a user</button>
          )}
        </div>
        <input type="search" className="search" placeholder="Search by name or email"
          aria-label="Search users" value={query} onChange={(event) => setQuery(event.target.value)} />
        {errorLine}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Status</th>
                <th scope="col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((user) => (
                <tr key={user.id}>
                  <td><strong>{user.full_name}</strong></td>
                  <td className="mono">{user.email}</td>
                  <td>
                    <select aria-label={`Role for ${user.full_name}`} value={user.role}
                      disabled={busy || user.id === currentUserId}
                      onChange={(event) => change(user, { role: event.target.value })}>
                      <RoleOptions />
                    </select>
                  </td>
                  <td><StatusStamp status={user.is_active ? 'ACTIVE' : 'INACTIVE'} /></td>
                  <td className="cell-actions">
                    <button type="button" className={user.is_active ? 'danger small' : 'small'}
                      disabled={busy || user.id === currentUserId}
                      onClick={() => change(user, { is_active: !user.is_active })}>
                      {user.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
