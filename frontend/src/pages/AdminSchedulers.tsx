import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminApi, type SchedulerJob } from '../api/auth';
import { Button, PageHeader, Skeleton } from '../components/ui/Primitives';
import { useToast } from '../components/ui/Toast';

function scheduleSummary(job: SchedulerJob): string {
  if (job.schedule_kind === 'interval') {
    const mins = Math.round((job.interval_seconds || 3600) / 60);
    if (mins < 60) return `Every ${mins} minutes`;
    const hours = Math.round(mins / 60);
    return hours === 1 ? 'Every hour' : `Every ${hours} hours`;
  }
  const hour = job.cron_hour && job.cron_hour !== '*' ? job.cron_hour : null;
  const minute = job.cron_minute && job.cron_minute !== '*' ? job.cron_minute : '0';
  if (hour && !hour.includes('*') && !hour.includes('/')) {
    return `Daily at ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;
  }
  if (minute.includes('*/30')) return 'Every 30 minutes';
  if (minute === '0' && hour === '*') return 'Every hour';
  return 'Custom schedule';
}

export default function AdminSchedulers() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-schedulers'],
    queryFn: adminApi.schedulers,
  });

  const updateMutation = useMutation({
    mutationFn: ({ key, patch }: { key: string; patch: Parameters<typeof adminApi.updateScheduler>[1] }) =>
      adminApi.updateScheduler(key, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-schedulers'] });
      toast.push('Settings saved', 'success');
    },
    onError: (err: Error) => toast.push(err.message, 'error'),
  });

  const seedMutation = useMutation({
    mutationFn: adminApi.seedSchedulers,
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['admin-schedulers'] });
      toast.push(res.seeded ? 'Default tasks loaded' : 'Tasks already configured', 'success');
    },
  });

  if (isLoading) {
    return (
      <>
        <PageHeader title="Background tasks" />
        <Skeleton className="skeleton-block" />
      </>
    );
  }

  if (error) {
    return (
      <>
        <PageHeader title="Background tasks" />
        <p className="form-error">{(error as Error).message}</p>
      </>
    );
  }

  const jobs = data ?? [];

  return (
    <>
      <PageHeader
        title="Background tasks"
        lead="Turn automatic updates on or off and adjust how often they run."
        actions={
          jobs.length === 0 ? (
            <Button variant="primary" onClick={() => seedMutation.mutate()} disabled={seedMutation.isPending}>
              Load defaults
            </Button>
          ) : undefined
        }
      />

      <div className="scheduler-list">
        {jobs.map((job) => (
          <article key={job.key} className="card scheduler-card">
            <div className="scheduler-card-head">
              <div>
                <h3>{job.name}</h3>
                <p className="muted-text">{job.description}</p>
                <p className="scheduler-meta">
                  <span className="badge">{job.category}</span>
                  <span className="schedule-pill">{scheduleSummary(job)}</span>
                </p>
              </div>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={job.is_enabled}
                  onChange={(e) =>
                    updateMutation.mutate({ key: job.key, patch: { is_enabled: e.target.checked } })
                  }
                />
                <span>{job.is_enabled ? 'On' : 'Off'}</span>
              </label>
            </div>

            <div className="scheduler-controls">
              <label>
                Frequency
                <select
                  value={job.schedule_kind}
                  onChange={(e) =>
                    updateMutation.mutate({
                      key: job.key,
                      patch: {
                        schedule_kind: e.target.value as 'cron' | 'interval',
                        interval_seconds: job.interval_seconds || 3600,
                      },
                    })
                  }
                >
                  <option value="cron">Scheduled time</option>
                  <option value="interval">Repeating interval</option>
                </select>
              </label>

              {job.schedule_kind === 'interval' ? (
                <label>
                  Run every (minutes)
                  <input
                    type="number"
                    min={1}
                    max={1440}
                    defaultValue={Math.round((job.interval_seconds || 3600) / 60)}
                    onBlur={(e) => {
                      const mins = Number(e.target.value);
                      if (!mins) return;
                      updateMutation.mutate({
                        key: job.key,
                        patch: { interval_seconds: mins * 60, schedule_kind: 'interval' },
                      });
                    }}
                  />
                </label>
              ) : (
                <>
                  <label>
                    Minute
                    <input
                      type="text"
                      defaultValue={job.cron_minute || '*'}
                      onBlur={(e) =>
                        updateMutation.mutate({ key: job.key, patch: { cron_minute: e.target.value } })
                      }
                    />
                  </label>
                  <label>
                    Hour
                    <input
                      type="text"
                      defaultValue={job.cron_hour || '*'}
                      onBlur={(e) =>
                        updateMutation.mutate({ key: job.key, patch: { cron_hour: e.target.value } })
                      }
                    />
                  </label>
                </>
              )}
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
