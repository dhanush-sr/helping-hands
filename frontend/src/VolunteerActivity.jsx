import { useEffect, useState } from 'react'
import { listMyAttendance } from './api.js'

export default function VolunteerActivity() {
  const [attendance, setAttendance] = useState([])
  const [error, setError] = useState('')
  useEffect(() => {
    listMyAttendance().then(setAttendance).catch((err) => setError(err.message))
  }, [])
  return (
    <section className="card">
      <h2>Attendance history</h2>
      <p className="error" role="alert">{error}</p>
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
