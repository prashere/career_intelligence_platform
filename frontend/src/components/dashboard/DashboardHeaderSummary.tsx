import type { DashboardResponse } from '../../api/client';

interface Props {
  dashboard?: DashboardResponse;
  deadlinesWeek?: number;
}

interface StatItem {
  label: string;
  value: number;
  tone?: 'default' | 'attention' | 'urgent';
}

export default function DashboardHeaderSummary({ dashboard, deadlinesWeek }: Props) {
  const newMatches = dashboard?.updated_cards.length ?? 0;
  const inProgress = dashboard?.in_progress.length ?? 0;
  const unread = dashboard?.notifications.filter((n) => !n.is_read).length ?? 0;
  const closingSoon = deadlinesWeek ?? 0;

  const stats: StatItem[] = [
    {
      label: 'New matches',
      value: newMatches,
      tone: newMatches > 0 ? 'attention' : 'default',
    },
    {
      label: 'In progress',
      value: inProgress,
      tone: inProgress > 0 ? 'attention' : 'default',
    },
    {
      label: 'Unread alerts',
      value: unread,
      tone: unread > 0 ? 'attention' : 'default',
    },
    {
      label: 'Closing within 7 days',
      value: closingSoon,
      tone: closingSoon > 0 ? 'urgent' : 'default',
    },
  ];

  return (
    <section className="dashboard-stats-bar card" aria-label="Dashboard summary">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className={`dashboard-stat${stat.tone !== 'default' ? ` dashboard-stat-${stat.tone}` : ''}`}
        >
          <span className="dashboard-stat-value">{stat.value}</span>
          <span className="dashboard-stat-label">{stat.label}</span>
        </div>
      ))}
    </section>
  );
}
