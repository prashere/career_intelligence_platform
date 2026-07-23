import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import OpportunityCard from '../components/OpportunityCard'

export default function Dashboard() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard })

  if (isLoading) return <div className="empty-state">Loading dashboard...</div>

  return (
    <>
      <div className="page-header"><h2>Dashboard</h2></div>

      <div className="dashboard-grid">
        <div className="dashboard-section">
          <h3>Updated Cards</h3>
          {data?.updated_cards.length ? (
            <div className="card-list">
              {data.updated_cards.slice(0, 5).map((opp) => (
                <OpportunityCard key={opp.id} opportunity={opp} onClick={() => navigate(`/opportunities/${opp.id}`)} />
              ))}
            </div>
          ) : (
            <p style={{ color: '#9aa0a6', fontSize: '0.875rem' }}>No new opportunities</p>
          )}
        </div>

        <div className="dashboard-section">
          <h3>In Progress</h3>
          {data?.in_progress.length ? (
            <div className="card-list">
              {data.in_progress.map((opp) => (
                <OpportunityCard key={opp.id} opportunity={opp} onClick={() => navigate(`/opportunities/${opp.id}`)} />
              ))}
            </div>
          ) : (
            <p style={{ color: '#9aa0a6', fontSize: '0.875rem' }}>No applications in progress</p>
          )}
        </div>

        <div className="dashboard-section">
          <h3>Upskilling</h3>
          {data?.upskilling.length ? (
            data.upskilling.map((item) => (
              <div key={item.id} style={{ marginBottom: '0.75rem' }}>
                <div style={{ fontSize: '0.875rem' }}>{item.title}</div>
                <div className="progress-bar">
                  <div className="progress-bar-fill" style={{ width: `${item.progress_percent}%` }} />
                </div>
                <div style={{ fontSize: '0.75rem', color: '#9aa0a6' }}>{item.progress_percent}% · {item.status}</div>
              </div>
            ))
          ) : (
            <p style={{ color: '#9aa0a6', fontSize: '0.875rem' }}>No learning items</p>
          )}
        </div>

        <div className="dashboard-section">
          <h3>Notifications</h3>
          {data?.notifications.length ? (
            data.notifications.slice(0, 5).map((n) => (
              <div key={n.id} className={`notification-item${n.is_read ? '' : ' unread'}`}>
                <strong>{n.title}</strong>
                <div style={{ color: '#9aa0a6', fontSize: '0.8125rem' }}>{n.body.slice(0, 100)}</div>
              </div>
            ))
          ) : (
            <p style={{ color: '#9aa0a6', fontSize: '0.875rem' }}>No notifications</p>
          )}
        </div>
      </div>
    </>
  )
}
