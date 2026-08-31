import { useCallback, useEffect, useState } from 'react'

import {
  assignTicket, getTicket, listEngineers, listTickets, resolveTicket, updateTicketStatus,
} from './api'

// Mirrors the 2a state machine in app/schemas.py: keys =current status, closed=terminal.
const TRANSITIONS = {
  open: ['open', 'in_progress', 'resolved', 'closed'],
  in_progress: ['open', 'in_progress', 'resolved', 'closed'],
  resolved: ['closed', 'in_progress'],
  closed: [],
}

const STATUS_LABEL = {
  open: 'Open',
  in_progress: 'In Progress',
  resolved: 'Resolved',
  closed: 'Closed',
}

function Badge({ kind, children }) {
  return <span className={`badge badge-${kind}`}>{children}</span>
}

function App() {
  const [tickets, setTickets] = useState(null)
  const [engineers, setEngineers] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
	const [actionMsg, setActionMsg] = useState(null)

  const engineerName = (id) =>
    engineers.length
      ? engineers.find((e) => e.id === id)?.name ?? 'â€”'
      : id ?? 'â€”'

  const refreshList = useCallback(async () => {
    try {
      const [list, engs] = await Promise.all([listTickets(), listEngineers()])
      setTickets(list)
      setEngineers(engs)
      setError(null)
    } catch (err) {
      setError(`Failed to load tickets: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadDetail = useCallback(async (id) => {
    try {
      const data = await getTicket(id)
      setDetail(data)
      setError(null)
    } catch (err) {
      setError(`Failed to load ticket #${id}: ${err.message}`)
    }
  }, [])

  const selectTicket = (id) => {
    setSelectedId(id)
    setDetail(null)
    loadDetail(id)
  }

  const doAssign = async (eid) => {
    if (!selectedId) return
    try {
      await assignTicket(selectedId, eid)
      setActionMsg(`Assigned #${selectedId} â†’ ${engineerName(eid)}`)
      await Promise.all([loadDetail(selectedId), refreshList()])
    } catch (err) {
      setError(`Assign failed: ${err.message}`)
    }
  }

	const doStatus = async (status) => {
    if (!selectedId || !status) return
    try {
      await updateTicketStatus(selectedId, status)
      setActionMsg(`#${selectedId} status â†’ ${STATUS_LABEL[status]}`)
      await Promise.all([loadDetail(selectedId), refreshList()])
    } catch (err) {
      setError(`Status update failed: ${err.message}`)
    }
	}

	const doResolve = async () => {
    if (!selectedId) return
    const resolution = window.prompt('Resolution text:', '')
    if (!resolution || !resolution.trim()) return
    try {
      await resolveTicket(selectedId, resolution.trim())
      setActionMsg(`#${selectedId} resolved`)
      await Promise.all([loadDetail(selectedId), refreshList()])
    } catch (err) {
      setError(`Resolve failed: ${err.message}`)
    }
	}

  useEffect(() => { refreshList() }, [refreshList])

  const d = detail
  const allowed = detail ? TRANSITIONS[detail.status] || [] : []
return (
    <div className="app">
      <style>{`
        .app { max-width: 1200px; margin: 0 auto; padding: 24px; font-family: system-ui, sans-serif; }
        h1, h2 { color: #111; }
        .loading { color: #555; padding: 24px; }
        .error { background: #fdecea; border: 1px solid #f5c6c7; color: #b3261e; padding: 10px 12px; border-radius:  â€Ž6px; margin:  â€Ž12px 0; }
        .banner { background: #eef4ff; border:  â€Ž1px solid #b8d4ff; color: #1a56a8; padding: 8px 12px; border-radius: 6px; margin-bottom: 12px; }
        table { width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.08); border-radius: 8px; overflow: hidden; }
        th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #eee; font-size: 14px; }
        th { background: #fafbfc; color: #555; font-weight: 600; }
        tbody tr:hover { background: #f7f9fc; cursor: pointer; }
        tr.selected td { background: #e9f2ff; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .badge-open { background: #e8f5e9; color: #1a7f37; }
        .badge-in_progress { background: #fff4e5; color: #b26a00; }
        .badge-resolved { background: #eef1f6; color: #444; }
        .badge-closed { background: #e6e6e6; color: #555; }
        .badge-sla-warning { background: #fff3cd; color: #8a6d00; }
        .badge-sla-breached { background: #fde8e6; color: #b3261e; }
        .layout { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 20px; }
        @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
        .detail { background: #fff; border-radius: 8px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,.08); font-size: 14px; min-height: 300px; }
        .detail h3 { margin: 16px 0 6px; color: #333; }
        .detail p { margin: 4px 0; }
        .detail pre { background: #f6f8fa; padding: 8px; border-radius: 6px; font-size: 13px; }
        .kv { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }
        .field { font-size: 13px; color: #444; }
        .field b { color: #111; }
        .actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 12px 0; }
        .actions button,.actions select { padding: 6px 10px; border-radius: 6px; border: 1px solid #ccc; background: #fff; font-size: 13px; cursor: pointer; }
        .actions button.primary { background: #1a56a8; color: #fff; border-color: #1a56a8; }
        .actions button.primary:disabled { background: #b9c4d6; cursor: not-allowed; }
        .sim { margin: 0; padding-left: 20px; }
        .sim li { margin: 4px 0; }
        .sim-score { color: #1a56a8; font-weight: 600; }
        .empty { color: #888; padding: 24px; }
      `}</style>
      <h1>TracePulse AI — Incident Dashboard</h1>
      {actionMsg && <div className="banner">OK {actionMsg}</div>}
      {error && <div className="error">ERROR {error}</div>}
{loading ? (
        <div className="loading">Loading tickets…</div>
      ) : error && !tickets ? (
        <div className="error">Unable to load data. Check the API is running.</div>
      ) : (
        <div className="layout">
          <section>
            <h2>Tickets ({tickets ? tickets.length : 0})</h2>
            {tickets && tickets.length === 0 && <div className="empty">No tickets yet.</div>}
            <table>
              <thead>
                <tr><th>ID</th><th>Title</th><th>Priority</th><th>Status</th><th>SLA</th><th>Engineer</th></tr>
              </thead>
              <tbody>
                {tickets && tickets.map((t) => (
                  <tr key={t.id} className={t.id === selectedId ? 'selected' : ''} onClick={() => selectTicket(t.id)}>
                    <td>{t.id}</td>
                    <td>{t.title}</td>
                    <td>{t.priority || '—'}</td>
                    <td><Badge kind={t.status}>{STATUS_LABEL[t.status] || t.status}</Badge></td>
                    <td>{t.sla_status ? <Badge kind={`sla-${t.sla_status}`}>{t.sla_status}</Badge> : '—'}</td>
                    <td>{engineerName(t.assigned_engineer_id)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="detail">
{!d ? (
              <div className="empty">Click a ticket to view details.</div>
            ) : (
              <>
                <h2>#{d.id} — {d.title}</h2>
                <div className="kv">
                  <span className="field"><b>Priority:</b> {d.priority || '—'}</span>
                  <span className="field"><b>Status:</b> <Badge kind={d.status}>{STATUS_LABEL[d.status] || d.status}</Badge></span>
                  <span className="field"><b>SLA:</b> {d.sla_status ? <Badge kind={`sla-${d.sla_status}`}>{d.sla_status}</Badge> : '—'}</span>
                  <span className="field"><b>Target:</b> {d.target_resolution_time ? new Date(d.target_resolution_time).toLocaleString() : '—'}</span>
                  <span className="field"><b>Engineer:</b> {engineerName(d.assigned_engineer_id)}</span>
                </div>
                <div className="actions">
<select
                    value="status"
                    onChange={(e) => doStatus(e.target.value)}
                    disabled={allowed.length === 0}
                    title={allowed.length === 0 ? 'Terminal status; no transitions allowed' : 'Change status'}>
                    <option value="status" disabled>Status…</option>
                    {allowed.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                  </select>
                  <select value="engineer" onChange={(e) => doAssign(Number(e.target.value))}>
                    <option value="engineer" disabled>Assign…</option>
                    {engineers.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </select>
                  <button className="primary" onClick={doResolve} disabled={d.status === 'closed' || d.status === 'resolved'}>
                    Resolve
                  </button>
                </div>
                <h3>Description</h3>
                <p>{d.description}</p>
                <h3>Logs</h3>
                <pre>{d.logs}</pre>
                <h3>RCA</h3>
                {d.root_cause ? (
                  <>
                    <p><b>Root cause:</b> {d.root_cause}</p>
                    <p><b>Evidence:</b> {d.evidence}</p>
                    <p><b>Area:</b> {d.issue_area || '—'}</p>
                    <p><b>Suggested resolution:</b> {d.suggested_resolution}</p>
                  </>
                ) : <p style={{ color: '#888' }}>No RCA computed yet.</p>}
                <h3>Similar incidents</h3>
                {d.similar_incidents && d.similar_incidents.length ? (
                  <ul className="sim">
                    {d.similar_incidents.map((s) => (
                      <li key={s.ticket_id}>
                        <span className="sim-score">{Math.round(s.similarity * 100)}%</span> — <b>#{s.ticket_id}</b> {s.title}
                      </li>
                    ))}
                  </ul>
                ) : <p style={{ color: '#888' }}>No similar incidents found.</p>}
              </>
          )}
          </section>
</div>
      )}
    </div>
  )
}

export default App
