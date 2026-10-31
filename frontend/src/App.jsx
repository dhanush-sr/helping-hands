import { useEffect, useState } from 'react'
import { getHealth } from './api.js'

function App() {
  const [health, setHealth] = useState({ state: 'loading' })

  useEffect(() => {
    getHealth()
      .then((data) => setHealth({ state: 'ok', data }))
      .catch((error) => setHealth({ state: 'error', message: error.message }))
  }, [])

  return (
    <main className="app">
      <h1>Helping Hands</h1>
      <p>Volunteer shifts for stores during busy periods.</p>

      <section className="status" aria-live="polite">
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
