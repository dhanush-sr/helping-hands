import { useState } from 'react'
import { signIn } from './api.js'

// Sign-in page (HH-11). Calls onSignedIn(user) after a successful sign-in.
function LoginForm({ onSignedIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      onSignedIn(await signIn(email, password))
    } catch (err) {
      setError(err.message)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card login" onSubmit={handleSubmit}>
      <h2>Sign in</h2>

      <label htmlFor="email">Email</label>
      <input
        id="email"
        type="email"
        autoComplete="username"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        required
      />

      <label htmlFor="password">Password</label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />

      <p className="error" role="alert" aria-live="assertive">
        {error}
      </p>

      <button type="submit" disabled={busy}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}

export default LoginForm
