import { useEffect, useState } from 'react'
import { getCurrentUser, getHealth, getToken, signOut } from './api.js'
import AdminPanel from './AdminPanel.jsx'
import LoginForm from './LoginForm.jsx'
import ShiftForm from './ShiftForm.jsx'

const ROLE_LABELS = {
  VOLUNTEER: 'Volunteer',
  STORE_MANAGER: 'Store manager',
  ADMIN: 'Admin',
}

function App() {
  const [health, setHealth] = useState({ state: 'loading' })
  // undefined while checking a saved token, null when signed out
  const [user, setUser] = useState(getToken() ? undefined : null)

  useEffect(() => {
    getHealth()
      .then((data) => setHealth({ state: 'ok', data }))
      .catch((error) => setHealth({ state: 'error', message: error.message }))
  }, [])

  useEffect(() => {
    if (!getToken()) return
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
  }, [])

  async function handleSignOut() {
    await signOut().catch(() => {})
    setUser(null)
  }

  return (
    <main className="app">
      <h1>Helping Hands</h1>
      <p>Volunteer shifts for stores during busy periods.</p>

      {user === undefined && <p>Checking your session…</p>}
      {user === null && <LoginForm onSignedIn={setUser} />}
      {user && (
        <section className="card" aria-live="polite">
          <p>
            Signed in as <strong>{user.full_name}</strong> ({ROLE_LABELS[user.role] ?? user.role})
          </p>
          <button type="button" onClick={handleSignOut}>
            Sign out
          </button>
        </section>
      )}
      {user?.role === 'ADMIN' && <AdminPanel />}
      {user?.role === 'STORE_MANAGER' && <ShiftForm />}

      <section className="card status" aria-live="polite">
        <h2>Backend status</h2>
        {health.state === 'loading' && <p>Checking…</p>}
        {health.state === 'ok' && (
          <p className="ok">
            API is up (version {health.data.version}, {health.data.environment})
          </p>
        )}
        {health.state === 'error' && (
          <p className="error">API not reachable: {health.message}</p>
        )}
      </section>
    </main>
  )
}

export default App
