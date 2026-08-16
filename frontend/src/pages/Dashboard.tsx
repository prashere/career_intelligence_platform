import { Link } from 'react-router-dom';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { intakeApi } from '../api/intake';
import OpportunityCard from '../components/OpportunityCard';
import { Button, KpiStrip, PageHeader, Skeleton } from '../components/ui/Primitives';

type FeedTab = 'all' | 'scholarships' | 'fellowships' | 'other';

export default function Dashboard() {
  const [search, setSearch] = useState('');
  const [funding, setFunding] = useState('');
  const [feedTab, setFeedTab] = useState<FeedTab>('all');
  const [feedQuery, setFeedQuery] = useState('');

  const { data, isLoading: dashboardLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: api.dashboard,
  });
  const { data: intakeStatus } = useQuery({
    queryKey: ['intake-status'],
    queryFn: intakeApi.status,
  });
  const {
    data: feed,
    isLoading: feedLoading,
    isFetching: feedFetching,
  } = useQuery({
    queryKey: ['feed', feedQuery, funding],
    queryFn: () => api.feed({ search: feedQuery || undefined, funding_type: funding || undefined }),
  });

  const feedItems = useMemo(() => {
    if (!feed) return [];
    if (feedTab === 'scholarships') return feed.scholarships;
    if (feedTab === 'fellowships') return feed.fellowships;
    if (feedTab === 'other') return feed.other;
    return [...feed.scholarships, ...feed.fellowships, ...feed.other];
  }, [feed, feedTab]);

  if (dashboardLoading) {
    return (
      <>
        <PageHeader eyebrow="Overview" title="Dashboard" />
        <Skeleton className="skeleton-kpi" />
        <div className="dashboard-grid">
          <Skeleton className="skeleton-block" />
          <Skeleton className="skeleton-block" />
        </div>
      </>
    );
  }

  const updated = data?.updated_cards.length ?? 0;
  const inProgress = data?.in_progress.length ?? 0;
  const unread = data?.notifications.filter((n) => !n.is_read).length ?? 0;
  const profileComplete = intakeStatus?.has_structured_profile ?? false;
  const feedSummary = feed?.summary;

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        lead="Your matches, deadlines, and personalized opportunity feed in one place."
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
          { label: 'New this week', value: feedSummary?.new_since ?? 'n/a' },
          { label: 'Deadlines ≤7d', value: feedSummary?.deadlines_this_week ?? 'n/a' },
        ]}
      />

      <section className="card dashboard-panel dashboard-priority">
        <h3 className="panel-title">Priority this week</h3>
        {data?.updated_cards.length ? (
          <div className="card-list">
            {data.updated_cards.slice(0, 4).map((opp) => (
              <OpportunityCard key={opp.id} opportunity={opp} />
            ))}
          </div>
        ) : (
          <p className="muted-text">
            No priority matches yet.{' '}
            <Link to="/profile/setup">Complete your profile</Link> or ask an admin to run ingestion.
          </p>
        )}
      </section>

      <section className="card dashboard-feed-section">
        <div className="dashboard-feed-head">
          <div>
            <h3 className="panel-title">Opportunities</h3>
            <p className="muted-text">Filtered by your profile envelope and eligibility rules.</p>
          </div>
          {feedFetching && <span className="feed-updating">Updating…</span>}
        </div>

        <form
          className="feed-filters"
          onSubmit={(e) => {
            e.preventDefault();
            setFeedQuery(search.trim());
          }}
        >
          <label>
            Search
            <input
              type="search"
              placeholder="Title, field, institution…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label>
            Funding
            <select value={funding} onChange={(e) => setFunding(e.target.value)}>
              <option value="">Any</option>
              <option value="full">Fully funded</option>
              <option value="partial">Partial</option>
            </select>
          </label>
          <Button type="submit" variant="primary">
            Apply
          </Button>
        </form>

        <div className="feed-tabs" role="tablist">
          {(['all', 'scholarships', 'fellowships', 'other'] as FeedTab[]).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={feedTab === key}
              className={`feed-tab${feedTab === key ? ' active' : ''}`}
              onClick={() => setFeedTab(key)}
            >
              {key === 'all' ? 'All' : key.charAt(0).toUpperCase() + key.slice(1)}
              {feed && key !== 'all' && (
                <span className="feed-tab-count">
                  {key === 'scholarships'
                    ? feed.scholarships.length
                    : key === 'fellowships'
                      ? feed.fellowships.length
                      : feed.other.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {feedLoading ? (
          <Skeleton className="skeleton-block" />
        ) : feedItems.length ? (
          <div className="card-list">
            {feedItems.map((opp) => (
              <OpportunityCard key={opp.id} opportunity={opp} />
            ))}
          </div>
        ) : (
          <p className="muted-text empty-feed-msg">
            No opportunities match your filters yet. Complete profile setup and run ingestion to populate your feed.
          </p>
        )}
      </section>

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
