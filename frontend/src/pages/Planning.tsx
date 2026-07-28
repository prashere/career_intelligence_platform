import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { PageHeader, Skeleton } from '../components/ui/Primitives';

export default function Planning() {
  const { data, isLoading } = useQuery({ queryKey: ['weekly'], queryFn: api.weeklyFocus });

  if (isLoading) return <Skeleton className="skeleton-block" />;

  return (
    <>
      <PageHeader eyebrow="Focus" title="Weekly Plan" lead={data?.focus_summary} />

      <div className="dashboard-grid">
        <section className="card dashboard-panel">
          <h3 className="panel-title">Deadlines this week</h3>
          {data?.deadlines.length ? data.deadlines.map((d) => (
            <div key={d.id} className="notification-item">
              <strong>{d.title}</strong>
              <p className="deadline-text">{new Date(d.deadline).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</p>
            </div>
          )) : <p className="muted-text">No deadlines this week</p>}
        </section>

        <section className="card dashboard-panel">
          <h3 className="panel-title">Prep tasks</h3>
          {data?.prep_tasks.length ? data.prep_tasks.map((t, i) => (
            <div key={i} className="notification-item">{t.title}</div>
          )) : <p className="muted-text">No prep tasks due</p>}
        </section>

        <section className="card dashboard-panel">
          <h3 className="panel-title">Learning in progress</h3>
          {data?.learning_tasks.length ? data.learning_tasks.map((t, i) => (
            <div key={i} className="learning-row">
              <span>{t.title}</span>
              <span className="muted-text">{t.progress}%</span>
            </div>
          )) : <p className="muted-text">No active learning</p>}
        </section>
      </div>
    </>
  );
}
