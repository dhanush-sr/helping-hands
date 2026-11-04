import { useEffect, useState } from 'react'
import { createUser, getRules, listUsers, saveRules, updateUser } from './api.js'

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

export default function AccountsAdmin({ currentUserId }) {
  const [users, setUsers] = useState([])
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

  return (
    <section className="card">
      <h2>Users and volunteering rules</h2>
      <p className="error" role="alert">{error}</p>
      <ul className="shift-list">
        {users.map((user) => (
          <li className="shift" key={user.id}>
            <strong>{user.full_name}</strong> · {user.email} · {user.is_active ? 'Active' : 'Inactive'}
            <select aria-label={`Role for ${user.full_name}`} value={user.role}
              disabled={busy || user.id === currentUserId}
              onChange={(event) => change(user, { role: event.target.value })}>
              <RoleOptions />
            </select>
            <button type="button" className="secondary" disabled={busy || user.id === currentUserId}
              onClick={() => change(user, { is_active: !user.is_active })}>
              {user.is_active ? 'Deactivate' : 'Activate'}
            </button>
          </li>
        ))}
      </ul>
      <form className="inline-form" onSubmit={(event) => {
        event.preventDefault()
        run(async () => {
          const created = await createUser(form)
          setUsers((rows) => [...rows, created])
          setForm(EMPTY)
        })
      }}>
        <h3>Add a user</h3>
        <label>Full name <input required maxLength={120} {...field('full_name')} /></label>
        <label>Email <input type="email" required maxLength={255} {...field('email')} /></label>
        <label>Temporary password
          <input type="password" autoComplete="new-password" required minLength={8}
            maxLength={72} {...field('password')} />
        </label>
        <label>Role <select {...field('role')}><RoleOptions /></select></label>
        <button disabled={busy}>Add user</button>
      </form>
      {rules && (
        <form className="inline-form" onSubmit={(event) => {
          event.preventDefault()
          run(async () => setRules(await saveRules(
            Object.fromEntries(Object.entries(rules).map(([key, value]) => [key, Number(value)])),
          )))
        }}>
          <h3>Volunteering rules</h3>
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
