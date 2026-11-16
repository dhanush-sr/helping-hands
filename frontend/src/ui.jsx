// Shared pieces of the "Exhibit Register" design: a state is a Stamp, a page opens with a
// PageHead, and missing data is an EmptyNote that says why it is missing.
import { AlertTriangle, Check, CircleDashed } from 'lucide-react'

const STAMP_ICON = { done: Check, failed: AlertTriangle, queued: CircleDashed }

// Every status the API sends, as [tone, label]. The border pattern carries the meaning.
const STATUS = {
  OPEN: ['info', 'Open'],
  FILLED: ['strong', 'Filled'],
  CANCELLED: ['rejected', 'Cancelled'],
  COMPLETED: ['done', 'Completed'],
  REQUESTED: ['queued', 'Requested'],
  CONFIRMED: ['strong', 'Confirmed'],
  DECLINED: ['rejected', 'Declined'],
  WITHDRAWN: ['skipped', 'Withdrawn'],
  ATTENDED: ['done', 'Attended'],
  NO_SHOW: ['failed', 'No-show'],
  NOT_RECORDED: ['lead', 'Not recorded'],
  ACTIVE: ['done', 'Active'],
  INACTIVE: ['skipped', 'Inactive'],
}

export function Stamp({ tone = 'info', children }) {
  const Icon = STAMP_ICON[tone]
  return (
    <span className="stamp" data-tone={tone}>
      {Icon && <Icon aria-hidden="true" />}
      {children}
    </span>
  )
}

export function StatusStamp({ status }) {
  const [tone, label] = STATUS[status] ?? ['info', String(status).toLowerCase()]
  return <Stamp tone={tone}>{label}</Stamp>
}

export function PageHead({ title, lede, actions }) {
  return (
    <header className="page-head">
      <span className="page-rule" aria-hidden="true" />
      <div className="page-head-row">
        <div>
          <h1>{title}</h1>
          {lede && <p className="lede">{lede}</p>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
    </header>
  )
}

export function EmptyNote({ title, children, action }) {
  return (
    <div className="empty-note">
      {title && <strong>{title}</strong>}
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

// At most one per page: the thing to know or do first.
export function Callout({ icon, step, title, children, action }) {
  return (
    <div className="callout">
      <span className="callout-icon" aria-hidden="true">
        {icon}
      </span>
      <div className="callout-body">
        <div className="callout-step">{step}</div>
        <div className="callout-title">{title}</div>
        <p>{children}</p>
      </div>
      {action}
    </div>
  )
}
