import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export default function Planning() {
  const { data, isLoading } = useQuery({ queryKey: ['weekly'], queryFn: api.weeklyFocus })

  if (isLoading) return <div className="empty-state">Loading weekly plan...</div>

  return (
    <>
      <div className="page-header"><h2>Weekly Focus</h2></div>
      <p className="summary-bar">{data?.focus_summary}</p>

      <div className="dashboard-grid">
        <div className="dashboard-section">
          <h3>Deadlines this week</h3>
          {data?.deadlines.length ? data.deadlines.map((d) => (
            <div key={d.id} className="notification-item">
              <strong>{d.title}</strong>
              <div style={{ color: '#f87171', fontSize: '0.8125rem' }}>{new Date(d.deadline).toLocaleDateString()}</div>
            </div>
          )) : <p style={{ color: '#9aa0a6', fontSize: '0.875rem' }}>No deadlines this week</p>}
        </div>

        <div className="dashboard-section">
          <h3>Prep tasks</h3>
          {data?.prep_tasks.length ? data.prep_tasks.map((t, i) => (
            <div key={i} className="notification-item">{t.title}</div>
          )) : <p style={{ color: '#9aa0a6', fontSize: '0.875rem' }}>No prep tasks due</p>}
        </div>

        <div className="dashboard-section">
          <h3>Learning in progress</h3>
          {data?.learning_tasks.length ? data.learning_tasks.map((t, i) => (
            <div key={i} className="notification-item">
              {t.title} — {t.progress}%
            </div>
          )) : <p style={{ color: '#9aa0a6', fontSize: '0.875rem' }}>No active learning</p>}
        </div>
      </div>
    </>
  )
}
