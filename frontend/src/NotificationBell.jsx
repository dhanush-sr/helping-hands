import { useCallback, useEffect, useState } from 'react'
import { listNotifications, markNotificationsRead } from './api.js'

// The bell everyone signed in sees (HH-27): a count of unread notices, and the list when
// opened. Opening it marks them read, so the count clears.
function NotificationBell() {
  const [unread, setUnread] = useState(0)
  const [notices, setNotices] = useState([])
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    listNotifications()
      .then((data) => {
        setUnread(data.unread)
        setNotices(data.notices)
      })
      .catch((err) => setError(err.message))
  }, [])

  useEffect(load, [load])

  async function toggle() {
    if (open) {
      setOpen(false)
      return
    }
    setOpen(true)
    setError('')
    try {
      const data = await markNotificationsRead()
      setUnread(data.unread)
      setNotices(data.notices)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section className="card">
      <button type="button" onClick={toggle} aria-expanded={open}>
        Notifications{unread > 0 ? ` (${unread} new)` : ''}
      </button>
      <p className="error" role="alert">
        {error}
      </p>
      {open && (
        <>
          {notices.length === 0 && <p>Nothing yet.</p>}
          <ul className="notices">
            {notices.map((notice) => (
              <li key={notice.id} className={notice.read_at ? 'muted' : ''}>
                {notice.message}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

export default NotificationBell
