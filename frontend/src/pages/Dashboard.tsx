import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { intakeApi } from '../api/intake';
import OpportunityCard from '../components/OpportunityCard';
import DashboardHeaderSummary from '../components/dashboard/DashboardHeaderSummary';
import MatchList from '../components/dashboard/MatchList';
import { Button, PageHeader, Skeleton } from '../components/ui/Primitives';

export default function Dashboard() {
  const { data, isLoading: dashboardLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: api.dashboard,
  });
  const { data: intakeStatus } = useQuery({
    queryKey: ['intake-status'],
    queryFn: intakeApi.status,
  });
  const { data: listPreview } = useQuery({
    queryKey: ['opportunities', 'matches', 'fit', 'preview'],
    queryFn: () => api.opportunities({ bucket: 'matches', sort: 'fit', limit: 20 }),
  });

  if (dashboardLoading) {
    return (
      <>
        <PageHeader eyebrow="Overview" title="Dashboard" />
        <Skeleton className="skeleton-kpi" />
        <Skeleton className="skeleton-block" />
      </>
    );
  }

  const profileComplete = intakeStatus?.has_structured_profile ?? false;
  const deadlinesWeek = listPreview?.items.filter(
    (o) => o.days_until_deadline != null && o.days_until_deadline <= 7,
  ).length;

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        lead="Ranked matches with explainable fit — every score tied to a reason from your profile."
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

      <DashboardHeaderSummary
        dashboard={data}
        newThisWeek={listPreview?.total}
        deadlinesWeek={deadlinesWeek}
      />

      {data?.updated_cards.length ? (
        <section className="card dashboard-panel dashboard-priority">
          <h3 className="panel-title">Priority this week</h3>
          <div className="card-list">
            {data.updated_cards.slice(0, 4).map((opp) => (
              <OpportunityCard key={opp.id} opportunity={opp} showRank />
            ))}
          </div>
        </section>
      ) : null}

      <MatchList />

      <div className="dashboard-layout dashboard-layout-bottom">
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
            data.notifications.slice(0, 6).map((n) => (
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
    </>
  );
}
