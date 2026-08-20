import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import {
  useOpportunityStatusMutation,
  type OpportunityStatus,
} from '../../hooks/useOpportunityStatusMutation';
import OpportunityCard from '../OpportunityCard';
import { Skeleton } from '../ui/Primitives';

export default function ClosingSoonSection() {
  const statusMutation = useOpportunityStatusMutation('closing_soon');

  const { data, isLoading } = useQuery({
    queryKey: ['opportunities', 'closing_soon'],
    queryFn: () =>
      api.opportunities({
        bucket: 'closing_soon',
        sort: 'deadline',
        limit: 12,
      }),
  });

  const items = data?.items ?? [];
  const unknownCount = data?.unknown_deadline_count ?? 0;

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

  if (isLoading) {
    return (
      <section className="dashboard-closing-section card">
        <Skeleton className="skeleton-block dashboard-match-skeleton" />
      </section>
    );
  }

  if (items.length === 0 && unknownCount === 0) {
    return null;
  }

  return (
    <section className="dashboard-closing-section card" aria-label="Closing soon">
      <div className="dashboard-closing-head">
        <div>
          <h3 className="panel-title">Closing soon</h3>
          <p className="dashboard-match-sub muted-text">
            Deadlines in the next two weeks. Saved and applied items appear here too.
          </p>
        </div>
        {items.length > 0 && (
          <span className="dashboard-match-count">{items.length} with dates</span>
        )}
      </div>

      {items.length > 0 ? (
        <div className="dashboard-match-list">
          {items.map((opp) => (
                  <OpportunityCard
                    key={`closing-${opp.id}`}
                    opportunity={opp}
                    onStatusChange={(status, dismissReason) =>
                handleStatusChange(opp.id, status, dismissReason)
              }
              statusPending={statusMutation.isPending}
            />
          ))}
        </div>
      ) : (
        <p className="dashboard-empty muted-text">No confirmed deadlines in the next two weeks.</p>
      )}

      {unknownCount > 0 && (
        <p className="dashboard-unknown-deadlines muted-text">
          {unknownCount} more {unknownCount === 1 ? 'match has' : 'matches have'} no confirmed
          deadline yet.
        </p>
      )}
    </section>
  );
}
