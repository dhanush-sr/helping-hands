import { useEffect, useState } from 'react'
import { listMyAttendance } from './api.js'
import { EmptyNote, StatusStamp } from './ui.jsx'

export default function VolunteerActivity() {
  const [attendance, setAttendance] = useState([])
  const [error, setError] = useState('')
  useEffect(() => {
    listMyAttendance().then(setAttendance).catch((err) => setError(err.message))
  }, [])
  return (
    <section className="card">
      <h2 className="sr-only">Attendance history</h2>
      <p className="error" role="alert">{error}</p>
      {attendance.length === 0 && !error && (
        <EmptyNote title="No attendance recorded yet">
          The store manager records it after each shift you work.
        </EmptyNote>
      )}
      {attendance.length > 0 && (
        <table>
          <thead>
            <tr><th scope="col">Date</th><th scope="col">Task</th><th scope="col">Hours</th><th scope="col">Outcome</th></tr>
          </thead>
          <tbody>
            {attendance.map((row) => (
              <tr key={row.shiftId}>
                <td>{row.date}</td>
                <td>{row.task}</td>
                <td>{row.hoursWorked}</td>
                <td><StatusStamp status={row.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
