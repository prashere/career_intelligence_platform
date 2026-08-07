import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { intakeApi } from '../api/intake';
import OpportunityCard from '../components/OpportunityCard';
import { Button, KpiStrip, PageHeader, Skeleton } from '../components/ui/Primitives';

export default function Dashboard() {
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard });
  const { data: intakeStatus } = useQuery({ queryKey: ['intake-status'], queryFn: intakeApi.status });

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
  const unread = data?.notifications.filter((n) => !n.is_read).length ?? 0;
  const profileComplete = intakeStatus?.has_structured_profile ?? false;

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        lead="Matches, deadlines, and applications at a glance."
        actions={
          !profileComplete ? (
            <Link to="/profile/setup">
              <Button variant="gold">Complete profile</Button>
            </Link>
          ) : undefined
        }
      />

      {!profileComplete && (
        <div className="banner banner-gold">
          <div>
            <strong>Profile setup incomplete</strong>
            <p className="muted-text">Finish your profile to unlock personalized opportunity matching.</p>
          </div>
          <Link to="/profile/setup">
            <Button variant="primary">Go to setup</Button>
          </Link>
        </div>
      )}

      <KpiStrip
        items={[
          { label: 'New matches', value: updated },
          { label: 'In progress', value: inProgress },
          { label: 'Unread alerts', value: unread },
          { label: 'Profile ready', value: profileComplete ? 'Yes' : 'No' },
        ]}
      />

      <div className="dashboard-layout">
        <section className="dashboard-primary card">
          <h3 className="panel-title">Priority this week</h3>
          {data?.updated_cards.length ? (
            <div className="card-list">
              {data.updated_cards.slice(0, 4).map((opp) => (
                <OpportunityCard key={opp.id} opportunity={opp} />
              ))}
            </div>
          ) : (
            <p className="muted-text">
              No matches yet.{' '}
              <Link to="/profile/setup">Complete your profile</Link> to get started.
            </p>
          )}
        </section>

        <div className="dashboard-secondary">
          <section className="card dashboard-panel">
            <h3 className="panel-title">In progress</h3>
            {data?.in_progress.length ? (
              <div className="card-list compact">
                {data.in_progress.map((opp) => (
                  <OpportunityCard key={opp.id} opportunity={opp} />
                ))}
              </div>
            ) : (
              <p className="muted-text">No active applications</p>
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
