import { useEffect, useState } from 'react'
import { listNotifications } from './api.js'

export default function VolunteerActivity() {
  const [notices, setNotices] = useState([])
  const [error, setError] = useState('')
  useEffect(() => {
    listNotifications().then(setNotices).catch((err) => setError(err.message))
  }, [])
  return (
    <section className="card">
      <h2>Notifications</h2>
      <p className="error" role="alert">{error}</p>
      {notices.length === 0 && <p>No notifications.</p>}
      <ul>{notices.map((notice) => <li key={notice.id}>{notice.message}</li>)}</ul>
    </section>
  )
}
