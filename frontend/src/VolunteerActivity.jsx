import { useEffect, useState } from 'react'
import { listMyAttendance, listNotifications } from './api.js'

export default function VolunteerActivity() {
  const [notices, setNotices] = useState([])
  const [attendance, setAttendance] = useState([])
  const [error, setError] = useState('')
  useEffect(() => {
    listNotifications().then(setNotices).catch((err) => setError(err.message))
    listMyAttendance().then(setAttendance).catch((err) => setError(err.message))
  }, [])
  return (
    <section className="card">
      <h2>Notifications</h2>
      <p className="error" role="alert">{error}</p>
      {notices.length === 0 && <p>No notifications.</p>}
      <ul>{notices.map((notice) => <li key={notice.id}>{notice.message}</li>)}</ul>
      <h2>Attendance history</h2>
      {attendance.length === 0 && <p>No attendance recorded.</p>}
      <ul>
        {attendance.map((row) => (
          <li key={row.shiftId}>{row.date} · {row.task} · {row.status === 'ATTENDED' ? 'Attended' : 'No-show'}
            {' '}· {row.hoursWorked} hours
          </li>
        ))}
      </ul>
    </section>
  )
}
