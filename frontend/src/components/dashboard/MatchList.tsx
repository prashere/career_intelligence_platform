import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { api, type Opportunity } from '../../api/client';
import {
  useOpportunityStatusMutation,
  type OpportunityStatus,
} from '../../hooks/useOpportunityStatusMutation';
import OpportunityCard from '../OpportunityCard';
import { Button, Skeleton } from '../ui/Primitives';
import FeedFilters, { readFiltersFromParams } from './FeedFilters';

export default function MatchList() {
  const [searchParams] = useSearchParams();
  const filters = readFiltersFromParams(searchParams);
  const statusMutation = useOpportunityStatusMutation(filters.bucket);

  const showPriority = filters.bucket === 'matches';

  const { data: dashboard } = useQuery({
    queryKey: ['dashboard'],
    queryFn: api.dashboard,
    enabled: showPriority,
  });

  const priorityItems: Opportunity[] = showPriority
    ? (dashboard?.updated_cards ?? []).slice(0, 4)
    : [];
  const priorityIds = new Set(priorityItems.map((o) => o.id));

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
  const allMatchItems = items.filter((o) => !priorityIds.has(o.id));
  const total = data?.pages[0]?.total ?? 0;

  function handleStatusChange(
    opportunityId: string,
    status: OpportunityStatus | 'new',
    dismissReason?: string,
  ) {
    statusMutation.mutate({
      opportunityId,
      status: status as OpportunityStatus,
      dismiss_reason: dismissReason,
    });
  }

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
      ) : (
        <>
          {showPriority && priorityItems.length > 0 && (
            <div className="dashboard-priority-block">
              <div className="dashboard-section-head">
                <h4 className="dashboard-section-title">Priority this week</h4>
                <p className="dashboard-section-sub muted-text">
                  Closing soon or newly matched. Act on these first.
                </p>
              </div>
              <div className="dashboard-match-list">
                {priorityItems.map((opp) => (
                  <OpportunityCard
                    key={`priority-${opp.id}`}
                    opportunity={opp}
                    variant="priority"
                    showRank
                    onStatusChange={(status, dismissReason) =>
                      handleStatusChange(opp.id, status, dismissReason)
                    }
                    statusPending={statusMutation.isPending}
                  />
                ))}
              </div>
            </div>
          )}

          <div className="dashboard-all-matches-block">
            {showPriority && priorityItems.length > 0 && allMatchItems.length > 0 && (
              <div className="dashboard-section-head">
                <h4 className="dashboard-section-title">All matches</h4>
              </div>
            )}

            {allMatchItems.length > 0 ? (
              <>
                <div className="dashboard-match-list">
                  {allMatchItems.map((opp) => (
                    <OpportunityCard
                      key={opp.id}
                      opportunity={opp}
                      showRank={filters.sort === 'fit' && filters.bucket === 'matches'}
                      onStatusChange={(status, dismissReason) =>
                        handleStatusChange(opp.id, status, dismissReason)
                      }
                      statusPending={statusMutation.isPending}
                      allowRestore={filters.bucket === 'dismissed'}
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
            ) : showPriority && priorityItems.length > 0 ? (
              <p className="dashboard-empty muted-text">
                No additional matches beyond your priority list right now.
              </p>
            ) : (
              <p className="dashboard-empty muted-text">
                No opportunities match these filters. Complete profile setup or try a different bucket.
              </p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
