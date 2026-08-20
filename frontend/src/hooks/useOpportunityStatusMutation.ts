import { useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query';
import { api, type DashboardResponse, type Opportunity, type OpportunityListResponse } from '../api/client';
import { useToast } from '../components/ui/Toast';
import type { Bucket } from '../components/dashboard/FeedFilters';

export type OpportunityStatus = 'new' | 'saved' | 'applied' | 'dismissed';

export const DISMISS_REASONS: { code: string; label: string }[] = [
  { code: 'wrong_field', label: 'Not my field' },
  { code: 'wrong_level', label: 'Wrong degree level' },
  { code: 'wrong_region', label: 'Wrong region' },
  { code: 'not_funded', label: 'Not funded enough' },
  { code: 'looks_fake', label: 'Looks fake or spam' },
  { code: 'other', label: 'Other reason' },
];

function statusActionLabel(status: OpportunityStatus, previousStatus?: string): string {
  if (status === 'saved') return 'Saved for later';
  if (status === 'applied') return 'Marked as applied';
  if (status === 'dismissed') return 'Dismissed';
  if (status === 'new' && previousStatus === 'saved') return 'Removed from saved';
  if (
    status === 'new' &&
    (previousStatus === 'applied' || previousStatus === 'in_progress')
  ) {
    return 'Application mark removed';
  }
  return 'Status updated';
}

function shouldRemoveFromBucket(bucket: Bucket, status: string): boolean {
  if (bucket === 'matches' && status === 'dismissed') return true;
  if (bucket === 'saved' && status !== 'saved') return true;
  if (bucket === 'applied' && status !== 'applied' && status !== 'in_progress') return true;
  if (bucket === 'dismissed' && status !== 'dismissed' && status !== 'archived') return true;
  if (bucket === 'closing_soon' && status === 'dismissed') return true;
  return false;
}

function patchOpportunity(opp: Opportunity, patch: Partial<Opportunity>): Opportunity {
  return { ...opp, ...patch };
}

function isInfiniteOpportunities(
  data: unknown,
): data is InfiniteData<OpportunityListResponse> {
  return (
    typeof data === 'object' &&
    data !== null &&
    'pages' in data &&
    Array.isArray((data as InfiniteData<OpportunityListResponse>).pages)
  );
}

export function useOpportunityStatusMutation(bucket: Bucket) {
  const queryClient = useQueryClient();
  const { push } = useToast();

  return useMutation({
    mutationFn: (vars: {
      opportunityId: string;
      status: OpportunityStatus;
      dismiss_reason?: string;
    }) =>
      api.updateStatus(vars.opportunityId, {
        status: vars.status,
        dismiss_reason: vars.dismiss_reason,
      }),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ['opportunities'], exact: false });
      await queryClient.cancelQueries({ queryKey: ['dashboard'] });

      const snapshots = queryClient.getQueriesData<InfiniteData<OpportunityListResponse>>({
        queryKey: ['opportunities'],
      });
      const dashboardSnapshot = queryClient.getQueryData<DashboardResponse>(['dashboard']);

      const remove = shouldRemoveFromBucket(bucket, vars.status);

      snapshots.forEach(([key, data]) => {
        if (!isInfiniteOpportunities(data)) return;
        queryClient.setQueryData(key, {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            items: remove
              ? page.items.filter((i) => i.id !== vars.opportunityId)
              : page.items.map((i) =>
                  i.id === vars.opportunityId
                    ? patchOpportunity(i, {
                        status: vars.status,
                        dismiss_reason: vars.dismiss_reason,
                      })
                    : i,
                ),
            total: remove ? Math.max(0, page.total - 1) : page.total,
          })),
        });
      });

      if (dashboardSnapshot) {
        const patch = { status: vars.status, dismiss_reason: vars.dismiss_reason };
        queryClient.setQueryData(['dashboard'], {
          ...dashboardSnapshot,
          updated_cards: dashboardSnapshot.updated_cards.map((i) =>
            i.id === vars.opportunityId ? patchOpportunity(i, patch) : i,
          ),
          in_progress: dashboardSnapshot.in_progress.map((i) =>
            i.id === vars.opportunityId ? patchOpportunity(i, patch) : i,
          ),
        });
      }

      const previousOpp =
        snapshots
          .flatMap(([, d]) => (isInfiniteOpportunities(d) ? d.pages.flatMap((p) => p.items) : []))
          .find((i) => i.id === vars.opportunityId) ??
        dashboardSnapshot?.updated_cards.find((i) => i.id === vars.opportunityId) ??
        dashboardSnapshot?.in_progress.find((i) => i.id === vars.opportunityId);

      return { snapshots, dashboardSnapshot, previousStatus: previousOpp?.status };
    },
    onError: (err, _vars, context) => {
      context?.snapshots?.forEach(([key, data]) => {
        if (data !== undefined) queryClient.setQueryData(key, data);
      });
      if (context?.dashboardSnapshot) {
        queryClient.setQueryData(['dashboard'], context.dashboardSnapshot);
      }
      const detail = err instanceof Error ? err.message : 'Unknown error';
      push(`Could not update status: ${detail.slice(0, 120)}`, 'error');
    },
    onSuccess: (_data, vars, context) => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'matches-preview'] });
      queryClient.invalidateQueries({ queryKey: ['opportunities', 'closing_soon'] });

      const label = statusActionLabel(vars.status, context?.previousStatus);

      const undoStatus = context?.previousStatus || 'new';
      const revertStatus =
        undoStatus === 'dismissed' || undoStatus === 'archived' ? 'new' : undoStatus;

      push(label, 'success', {
        label: 'Undo',
        onClick: () => {
          api
            .updateStatus(vars.opportunityId, { status: revertStatus })
            .then(() => {
              queryClient.invalidateQueries({ queryKey: ['opportunities'] });
              queryClient.invalidateQueries({ queryKey: ['dashboard'] });
            })
            .catch(() => push('Undo failed', 'error'));
        },
      });
    },
  });
}
