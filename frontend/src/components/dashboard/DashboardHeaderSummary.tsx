import type { DashboardResponse } from '../../api/client';
import { KpiStrip } from '../ui/Primitives';

interface Props {
  dashboard?: DashboardResponse;
  newThisWeek?: number;
  deadlinesWeek?: number;
}

export default function DashboardHeaderSummary({ dashboard, newThisWeek, deadlinesWeek }: Props) {
  const updated = dashboard?.updated_cards.length ?? 0;
  const inProgress = dashboard?.in_progress.length ?? 0;
  const unread = dashboard?.notifications.filter((n) => !n.is_read).length ?? 0;

  return (
    <KpiStrip
      items={[
        { label: 'New matches', value: updated },
        { label: 'In progress', value: inProgress },
        { label: 'Unread alerts', value: unread },
        { label: 'New this week', value: newThisWeek ?? 'n/a' },
        { label: 'Deadlines ≤7d', value: deadlinesWeek ?? 'n/a' },
      ]}
    />
  );
}
