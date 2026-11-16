import { useEffect, useState } from 'react'
import {
  BarChart3, CalendarCheck, CalendarDays, CalendarRange, ClipboardList, History, LogOut, Menu,
  PlusCircle, Search, Settings2, Store, Users, X,
} from 'lucide-react'
import { getCurrentUser, getHealth, getToken, signOut } from './api.js'
import { BusyPeriodsAdmin, StoresAdmin } from './AdminPanel.jsx'
import AuditLog from './AuditLog.jsx'
import LoginForm from './LoginForm.jsx'
import MySchedule from './MySchedule.jsx'
import NotificationBell from './NotificationBell.jsx'
import Reports from './Reports.jsx'
import AccountsAdmin from './AccountsAdmin.jsx'
import ManagerShifts from './ManagerShifts.jsx'
import ShiftForm from './ShiftForm.jsx'
import VolunteerActivity from './VolunteerActivity.jsx'
import ShiftList from './ShiftList.jsx'
import { Callout, PageHead } from './ui.jsx'

const ROLE_LABELS = {
  VOLUNTEER: 'Volunteer',
  STORE_MANAGER: 'Store manager',
  ADMIN: 'Admin',
}

// Each role's pages, in rail order. `group` is the rail heading the page sits under.
// render(ctx) gets { user, go, bump, version }.
const PAGES = {
  VOLUNTEER: [
    { key: 'find', group: 'Shifts', label: 'Find shifts', icon: Search,
      lede: 'Open shifts at every store. Sign up and the store manager confirms it.',
      render: ({ version }) => <ShiftList key={version} canSignUp /> },
    { key: 'schedule', group: 'Shifts', label: 'My schedule', icon: CalendarCheck,
      lede: 'Shifts you have asked for or been confirmed on, and your hours this week.',
      render: ({ bump }) => <MySchedule onChanged={bump} /> },
    { key: 'attendance', group: 'Shifts', label: 'Attendance history', icon: History,
      lede: 'Shifts you worked, as recorded by the store manager.',
      render: () => <VolunteerActivity /> },
  ],
  STORE_MANAGER: [
    { key: 'post', group: 'Shifts', label: 'Post a shift', icon: PlusCircle,
      lede: 'Ask for volunteers at your store. They see it under Find shifts straight away.',
      render: ({ go, bump }) => <ShiftForm onSaved={() => { bump(); go('manage') }} /> },
    { key: 'manage', group: 'Shifts', label: 'My shifts', icon: ClipboardList,
      lede: 'Approve sign-ups, edit or cancel shifts, and record attendance once a shift starts.',
      actions: ({ go }) => <PostButton go={go} />,
      render: ({ bump }) => <ManagerShifts onChanged={bump} /> },
    { key: 'open', group: 'Shifts', label: 'All open shifts', icon: CalendarDays,
      lede: 'What volunteers see, across every store.',
      render: ({ version }) => <ShiftList key={version} /> },
    { key: 'reports', group: 'Insights', label: 'Reports', icon: BarChart3,
      lede: 'Coverage, hours and no-shows for your store. Download any of them as CSV.',
      render: () => <Reports /> },
  ],
  ADMIN: [
    { key: 'shifts', group: 'Shifts', label: 'All open shifts', icon: CalendarDays,
      lede: 'Every open shift across the stores.',
      render: ({ version, go }) => (
        <>
          <Callout icon={<Store size={22} />} step="How shifts get posted"
            title="Store managers post shifts for their own store"
            action={<button type="button" onClick={() => go('stores')}>Assign managers</button>}>
            Admins set up the stores, busy periods and rules. A shift is posted by the manager of
            its store, so every store needs a manager before it can ask for help.
          </Callout>
          <ShiftList key={version} />
        </>
      ) },
    { key: 'users', group: 'People', label: 'Users', icon: Users,
      lede: 'Add people, change their role, or deactivate an account.',
      render: ({ user }) => <AccountsAdmin view="users" currentUserId={user.id} /> },
    { key: 'rules', group: 'People', label: 'Volunteering rules', icon: Settings2,
      lede: 'Limits every sign-up is checked against.',
      render: ({ user }) => <AccountsAdmin view="rules" currentUserId={user.id} /> },
    { key: 'stores', group: 'Setup', label: 'Stores', icon: Store,
      lede: 'Each store and the manager who posts its shifts.',
      render: () => <StoresAdmin /> },
    { key: 'periods', group: 'Setup', label: 'Busy periods', icon: CalendarRange,
      lede: 'Weekends and festivals that shifts are posted for.',
      render: () => <BusyPeriodsAdmin /> },
    { key: 'reports', group: 'Insights', label: 'Reports', icon: BarChart3,
      lede: 'Coverage, hours and no-shows across all stores. Download any of them as CSV.',
      render: () => <Reports /> },
    { key: 'audit', group: 'Insights', label: 'Audit history', icon: History,
      lede: 'Every change to shifts, decisions, attendance and roles, and who made it.',
      render: () => <AuditLog /> },
  ],
}

function PostButton({ go }) {
  return (
    <button type="button" className="primary" onClick={() => go('post')}>
      <PlusCircle aria-hidden="true" /> Post a shift
    </button>
  )
}

function App() {
  const [version, setVersion] = useState(0)
  const [health, setHealth] = useState({ state: 'loading' })
  // undefined while checking a saved token, null when signed out
  const [user, setUser] = useState(getToken() ? undefined : null)
  const [pageKey, setPageKey] = useState(() => window.location.hash.slice(1))
  const [drawer, setDrawer] = useState(false)
  const [folded, setFolded] = useState(() => localStorage.getItem('hh-rail') === 'hidden')

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
    go('')
  }

  function go(key) {
    setPageKey(key)
    setDrawer(false)
    window.history.replaceState(null, '', key ? `#${key}` : window.location.pathname)
  }

  function toggleRail() {
    if (window.matchMedia('(min-width: 1024px)').matches) {
      localStorage.setItem('hh-rail', folded ? 'shown' : 'hidden')
      setFolded(!folded)
    } else {
      setDrawer(!drawer)
    }
  }

  const status = (
    <p className="api-status" aria-live="polite">
      {health.state === 'loading' && 'Checking the API…'}
      {health.state === 'ok' && <span className="ok-dot">API online · v{health.data.version}</span>}
      {health.state === 'error' && <span className="error">API not reachable: {health.message}</span>}
    </p>
  )

  if (!user) {
    return (
      <div className="signin-page">
        <div className="signin-brand">
          <span className="mark" aria-hidden="true">H</span>
          <div>
            <div className="wordmark">Helping Hands</div>
            <div className="tagline">Store volunteering</div>
          </div>
        </div>
        {user === undefined ? <p className="muted">Checking your session…</p> : <LoginForm onSignedIn={setUser} />}
        {status}
      </div>
    )
  }

  const pages = PAGES[user.role] ?? []
  const page = pages.find((p) => p.key === pageKey) ?? pages[0]
  const ctx = { user, go, version, bump: () => setVersion((n) => n + 1) }
  const groups = [...new Set(pages.map((p) => p.group))]

  const nav = (
    <nav aria-label="Main" className="rail-nav">
      {groups.map((group) => (
        <div className="rail-group" key={group}>
          <div className="rail-label"><span>{group}</span></div>
          <ul>
            {pages.filter((p) => p.group === group).map((p) => (
              <li key={p.key}>
                <button type="button" className={`rail-item${p === page ? ' active' : ''}`}
                  aria-current={p === page ? 'page' : undefined} onClick={() => go(p.key)}>
                  <p.icon aria-hidden="true" />
                  <span>{p.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {status}
    </nav>
  )

  const brand = (
    <div className="rail-brand">
      <span className="mark" aria-hidden="true">H</span>
      <div>
        <div className="wordmark">Helping Hands</div>
        <div className="tagline">{ROLE_LABELS[user.role]} console</div>
      </div>
    </div>
  )

  return (
    <div className={`shell${folded ? ' folded' : ''}`}>
      <aside className="rail" aria-label="Navigation">
        {brand}
        {nav}
      </aside>

      {drawer && (
        <>
          <div className="scrim" onClick={() => setDrawer(false)} aria-hidden="true" />
          <aside className="rail drawer" aria-label="Navigation">
            <div className="drawer-head">
              {brand}
              <button type="button" className="icon-button quiet" aria-label="Close menu"
                onClick={() => setDrawer(false)}>
                <X aria-hidden="true" />
              </button>
            </div>
            {nav}
          </aside>
        </>
      )}

      <div className="main-col">
        <header className="topbar">
          <button type="button" className="icon-button quiet" aria-label="Show or hide the menu"
            onClick={toggleRail}>
            <Menu aria-hidden="true" />
          </button>
          <nav aria-label="Breadcrumb" className="crumbs">
            <span>{page.group}</span>
            <span aria-hidden="true">›</span>
            <strong>{page.label}</strong>
          </nav>
          <div className="topbar-actions">
            <NotificationBell />
            <div className="account">
              <span className="initial" aria-hidden="true">{user.full_name.slice(0, 1)}</span>
              <span className="account-name">
                {user.full_name}
                <small>{ROLE_LABELS[user.role] ?? user.role}</small>
              </span>
            </div>
            <button type="button" className="quiet" onClick={handleSignOut}>
              <LogOut aria-hidden="true" /> <span className="hide-sm">Sign out</span>
            </button>
          </div>
        </header>

        <main className="page" key={page.key}>
          <PageHead title={page.label} lede={page.lede} actions={page.actions?.(ctx)} />
          {page.render(ctx)}
        </main>
      </div>
    </div>
  )
}

export default App
