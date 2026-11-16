import { useCallback, useEffect, useState } from 'react'
import { API_BASE_URL, getReport, getToken, listBusyPeriods, listStores } from './api.js'
import { EmptyNote, StatusStamp } from './ui.jsx'
import ReportSummary from './ReportCharts.jsx'

const TABS = [
  { name: 'coverage', label: 'Coverage' },
  { name: 'hours', label: 'Hours per volunteer' },
  { name: 'no-shows', label: 'No-shows' },
]

const HEADINGS = {
  shift_id: 'Shift',
  busy_period: 'Busy period',
  start_time: 'From',
  end_time: 'To',
  slots_needed: 'Needed',
  open_slots: 'Still open',
  volunteer_id: 'Id',
  no_shows: 'No-shows',
  hours_worked: 'Hours',
}

function heading(column) {
  return HEADINGS[column] ?? column.replaceAll('_', ' ')
}

// Coverage and volunteer reports (HH-32), for store managers and admins.
function Reports() {
  const [tab, setTab] = useState('coverage')
  const [filters, setFilters] = useState({ storeId: '', busyPeriodId: '', since: '', until: '' })
  const [data, setData] = useState(null)
  const [stores, setStores] = useState([])
  const [periods, setPeriods] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([listStores(), listBusyPeriods()])
      .then(([storeList, periodList]) => {
        setStores(storeList)
        setPeriods(periodList)
      })
      .catch((err) => setError(err.message))
  }, [])

  const load = useCallback(() => {
    getReport(tab, filters)
      .then((report) => {
        // Remember which report these rows belong to: on a tab switch the old rows are
        // still on screen until the new ones arrive.
        setData({ ...report, tab })
        setError('')
      })
      .catch((err) => {
        setError(err.message)
        setData(null)
      })
  }, [tab, filters])

  useEffect(load, [load])

  function set(name) {
    return {
      id: `report-${name}`,
      value: filters[name],
      onChange: (event) => setFilters({ ...filters, [name]: event.target.value }),
    }
  }

  // The download needs the same filters and the bearer token, so fetch it and save the blob.
  async function download() {
    setError('')
    const query = new URLSearchParams(
      Object.entries(filters).filter(([, value]) => value !== ''),
    ).toString()
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/reports/${tab}.csv${query ? `?${query}` : ''}`,
        { headers: { Authorization: `Bearer ${getToken()}` } },
      )
      if (!response.ok) throw new Error(`Download failed with status ${response.status}`)
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = `${tab}.csv`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
    <section className="card report-controls">
      <h2 className="sr-only">Reports</h2>

      <div className="tabs">
        {TABS.map((item) => (
          <button
            key={item.name}
            type="button"
            className={item.name === tab ? 'active' : ''}
            aria-current={item.name === tab ? 'page' : undefined}
            onClick={() => setTab(item.name)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="filters">
        <div>
          <label htmlFor="report-storeId">Store</label>
          <select {...set('storeId')}>
            <option value="">All I can see</option>
            {stores.map((store) => (
              <option key={store.id} value={store.id}>
                {store.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="report-busyPeriodId">Busy period</label>
          <select {...set('busyPeriodId')}>
            <option value="">Any</option>
            {periods.map((period) => (
              <option key={period.id} value={period.id}>
                {period.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="report-since">From</label>
          <input type="date" {...set('since')} />
        </div>
        <div>
          <label htmlFor="report-until">To</label>
          <input type="date" {...set('until')} />
        </div>
        <button type="button" onClick={download}>
          Download CSV
        </button>
      </div>
    </section>

      <p className="error" role="alert">
        {error}
      </p>
      {data && data.rows.length === 0 && !error && (
        <EmptyNote title="Nothing to report for these filters">Widen the dates or pick another store.</EmptyNote>
      )}

      {data && data.rows.length > 0 && <ReportSummary tab={data.tab} rows={data.rows} />}

      {data && data.rows.length > 0 && (
        <section className="card">
        <h3 className="section-title">All rows <span className="count">{data.rows.length}</span></h3>
        <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {data.columns.map((column) => (
                <th scope="col" key={column}>
                  {heading(column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, index) => (
              <tr key={row.shift_id ?? row.volunteer_id ?? index}>
                {data.columns.map((column) => (
                  <td key={column}>
                    {column === 'status' ? <StatusStamp status={row[column]} /> : row[column] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        </section>
      )}
    </>
  )
}

export default Reports
