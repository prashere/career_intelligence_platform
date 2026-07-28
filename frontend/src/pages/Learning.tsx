import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Button, PageHeader, Skeleton } from '../components/ui/Primitives';

export default function Learning() {
  const [title, setTitle] = useState('');
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ['learning'], queryFn: api.learning });

  const createMutation = useMutation({
    mutationFn: api.createLearning,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['learning'] });
      setTitle('');
    },
  });

  if (isLoading) return <Skeleton className="skeleton-block" />;

  return (
    <>
      <PageHeader eyebrow="Grow" title="Upskilling" lead="Track courses and certifications that strengthen your profile." />

      <div className="filter-bar">
        <input className="form-control" placeholder="Add course or certification…" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Button variant="primary" onClick={() => title && createMutation.mutate({ title, item_type: 'course' })}>Add</Button>
      </div>

      <section className="card dashboard-panel">
        {data?.length ? data.map((item) => (
          <div key={item.id} className="learning-row">
            <div className="learning-row-head">
              <span>{item.title}</span>
              <span className="muted-text">{item.item_type} · {item.status}</span>
            </div>
            <div className="progress-bar">
              <div className="progress-bar-fill" style={{ width: `${item.progress_percent}%` }} />
            </div>
            {item.outcome_notes && <p className="muted-text">{item.outcome_notes}</p>}
          </div>
        )) : <p className="muted-text">No learning items yet — add your first course above.</p>}
      </section>
    </>
  );
}
