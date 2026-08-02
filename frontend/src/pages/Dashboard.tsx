import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, Opportunity } from '../api/client';
import OpportunityCard from '../components/OpportunityCard';
import { KpiStrip, PageHeader, Skeleton } from '../components/ui/Primitives';

export default function Dashboard() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard });

  if (isLoading) {
    return (
      <>
        <PageHeader eyebrow="Overview" title="Dashboard" />
        <Skeleton className="skeleton-kpi" />
        <div className="dashboard-grid"><Skeleton className="skeleton-block" /><Skeleton className="skeleton-block" /></div>
      </>
    );
  }

  const updated = data?.updated_cards.length ?? 0;
  const inProgress = data?.in_progress.length ?? 0;
  const learning = data?.upskilling.length ?? 0;
  const unread = data?.notifications.filter((n) => !n.is_read).length ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        lead="Your week at a glance — new matches, active applications, and prep."
      />

      <KpiStrip
        items={[
          { label: 'New matches', value: updated },
          { label: 'In progress', value: inProgress },
          { label: 'Learning items', value: learning },
          { label: 'Unread alerts', value: unread },
        ]}
      />

      <div className="dashboard-layout">
        <section className="dashboard-primary card">
          <h3 className="panel-title">Priority this week</h3>
          {data?.updated_cards.length ? (
            <div className="card-list">
              {data.updated_cards.slice(0, 4).map((opp) => (
                <OpportunityCard key={opp.id} opportunity={opp} onClick={() => navigate(`/opportunities/${opp.id}`)} />
              ))}
            </div>
          ) : (
            <p className="muted-text">No new high-priority matches. Check back after updating your profile.</p>
          )}
        </section>

        <div className="dashboard-secondary">
          <section className="card dashboard-panel">
            <h3 className="panel-title">In progress</h3>
            {data?.in_progress.length ? (
              <div className="card-list compact">
                {data.in_progress.map((opp) => (
                  <OpportunityCard key={opp.id} opportunity={opp} onClick={() => navigate(`/opportunities/${opp.id}`)} />
                ))}
              </div>
            ) : (
              <p className="muted-text">No active applications</p>
            )}
          </section>

          <section className="card dashboard-panel">
            <h3 className="panel-title">Upskilling</h3>
            {data?.upskilling.length ? (
              data.upskilling.map((item) => (
                <div key={item.id} className="learning-row">
                  <div className="learning-row-head">
                    <span>{item.title}</span>
                    <span className="muted-text">{item.progress_percent}%</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-bar-fill" style={{ width: `${item.progress_percent}%` }} />
                  </div>
                </div>
              ))
            ) : (
              <p className="muted-text">No learning items tracked</p>
            )}
          </section>

          <section className="card dashboard-panel">
            <h3 className="panel-title">Notifications</h3>
            {data?.notifications.length ? (
              data.notifications.slice(0, 5).map((n) => (
                <div key={n.id} className={`notification-item${n.is_read ? '' : ' unread'}`}>
                  <strong>{n.title}</strong>
                  <p className="muted-text">{n.body.slice(0, 120)}</p>
                </div>
              ))
            ) : (
              <p className="muted-text">All caught up</p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
