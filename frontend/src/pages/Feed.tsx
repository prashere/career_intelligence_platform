import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { api, Opportunity } from '../api/client';
import { CardList } from '../components/OpportunityCard';
import { Button, EmptyState, KpiStrip, PageHeader, Skeleton } from '../components/ui/Primitives';

type FitFilter = 'all' | 'strong' | 'moderate';
type SortKey = 'fit' | 'deadline';

function applyFilters(items: Opportunity[], fitFilter: FitFilter, sortKey: SortKey) {
  let list = [...items];
  if (fitFilter !== 'all') list = list.filter((o) => o.fit_level === fitFilter);
  if (sortKey === 'fit') list.sort((a, b) => (b.fit_score ?? 0) - (a.fit_score ?? 0));
  return list;
}

export default function Feed() {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [fitFilter, setFitFilter] = useState<FitFilter>('all');
  const [sortKey, setSortKey] = useState<SortKey>('fit');
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['feed', query],
    queryFn: () => api.feed(query || undefined),
  });

  const scholarships = useMemo(
    () => applyFilters(data?.scholarships ?? [], fitFilter, sortKey),
    [data, fitFilter, sortKey],
  );
  const fellowships = useMemo(
    () => applyFilters(data?.fellowships ?? [], fitFilter, sortKey),
    [data, fitFilter, sortKey],
  );
  const other = useMemo(
    () => applyFilters(data?.other ?? [], fitFilter, sortKey),
    [data, fitFilter, sortKey],
  );
  const total = scholarships.length + fellowships.length + other.length;

  if (isLoading) {
    return (
      <>
        <PageHeader eyebrow="Discover" title="Opportunities" />
        <Skeleton className="skeleton-kpi" />
        <Skeleton className="skeleton-block" />
      </>
    );
  }

  if (error) {
    return (
      <EmptyState
        title="Could not load opportunities"
        description="Make sure the API is running (docker compose up)."
        action={<Button variant="secondary" onClick={() => window.location.reload()}>Retry</Button>}
      />
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Discover"
        title="Opportunities"
        lead="Fully funded programs matched to your profile — ranked by fit and urgency."
        actions={<Link to="/profile/intake"><Button variant="gold">Complete profile</Button></Link>}
      />

      {data && (
        <KpiStrip
          items={[
            { label: 'New this week', value: data.summary.new_since },
            { label: 'Deadlines soon', value: data.summary.deadlines_this_week },
            { label: 'Prep due', value: data.summary.prep_milestones_due },
            { label: 'Showing', value: total },
          ]}
        />
      )}

      <div className="filter-bar">
        <input
          className="form-control filter-search"
          placeholder="Search by title, institution, field…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && setQuery(search)}
        />
        <div className="filter-chips">
          {(['all', 'strong', 'moderate'] as FitFilter[]).map((f) => (
            <button
              key={f}
              type="button"
              className={`chip${fitFilter === f ? ' selected' : ''}`}
              onClick={() => setFitFilter(f)}
            >
              {f === 'all' ? 'All fits' : f === 'strong' ? 'Strong fit' : 'Moderate'}
            </button>
          ))}
        </div>
        <select className="form-control filter-sort" value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
          <option value="fit">Sort by match</option>
          <option value="deadline">Sort by deadline</option>
        </select>
        <Button variant="primary" onClick={() => setQuery(search)}>Search</Button>
      </div>

      {total === 0 ? (
        <EmptyState
          title="No opportunities yet"
          description="Complete your profile intake to enable matching, or trigger ingestion to populate the feed."
          action={
            <Link to="/profile/intake">
              <Button variant="gold">Start profile intake</Button>
            </Link>
          }
        />
      ) : (
        <>
          <CardList title="Scholarships" items={scholarships} onSelect={(id) => navigate(`/opportunities/${id}`)} />
          <CardList title="Fellowships" items={fellowships} onSelect={(id) => navigate(`/opportunities/${id}`)} />
          <CardList title="Other programs" items={other} onSelect={(id) => navigate(`/opportunities/${id}`)} />
        </>
      )}
    </>
  );
}
