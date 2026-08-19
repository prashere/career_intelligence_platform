import { useInfiniteQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { api, type Opportunity } from '../../api/client';
import OpportunityCard from '../OpportunityCard';
import { Button, Skeleton } from '../ui/Primitives';
import FeedFilters, { readFiltersFromParams } from './FeedFilters';

export default function MatchList() {
  const [searchParams] = useSearchParams();
  const filters = readFiltersFromParams(searchParams);

  const queryKey = [
    'opportunities',
    filters.bucket,
    filters.sort,
    filters.search,
    filters.opportunity_type,
    filters.funding_type,
    filters.verified_only,
  ];

  const {
    data,
    isLoading,
    isFetching,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) =>
      api.opportunities({
        bucket: filters.bucket,
        sort: filters.sort,
        search: filters.search || undefined,
        opportunity_type: filters.opportunity_type || undefined,
        funding_type: filters.funding_type || undefined,
        verified_only: filters.verified_only,
        cursor: pageParam as string | undefined,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: (prev) => prev,
  });

  const items: Opportunity[] = data?.pages.flatMap((p) => p.items) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  return (
    <section className="dashboard-match-section card">
      <div className="dashboard-match-head">
        <div>
          <h3 className="panel-title">Your matches</h3>
          <p className="dashboard-match-sub muted-text">
            Ranked by fit with explainable reasons from your profile.
          </p>
        </div>
        <div className="dashboard-match-meta">
          {isFetching && !isLoading && <span className="dashboard-updating">Updating…</span>}
          <span className="dashboard-match-count">{total} total</span>
        </div>
      </div>

      <FeedFilters onApply={() => { /* URL drives refetch */ }} />

      {isLoading ? (
        <Skeleton className="skeleton-block dashboard-match-skeleton" />
      ) : items.length ? (
        <>
          <div className="dashboard-match-list">
            {items.map((opp) => (
              <OpportunityCard
                key={opp.id}
                opportunity={opp}
                showRank={filters.sort === 'fit' && filters.bucket === 'matches'}
              />
            ))}
          </div>
          {hasNextPage && (
            <div className="dashboard-load-more-wrap">
              <Button
                variant="secondary"
                className="dashboard-load-more"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
              >
                {isFetchingNextPage ? 'Loading…' : 'Load more'}
              </Button>
            </div>
          )}
        </>
      ) : (
        <p className="dashboard-empty muted-text">
          No opportunities match these filters. Complete profile setup or try a different bucket.
        </p>
      )}
    </section>
  );
}
