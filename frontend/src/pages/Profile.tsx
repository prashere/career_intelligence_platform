import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export default function Profile() {
  const queryClient = useQueryClient();
  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: api.profile });
  const [form, setForm] = useState<Record<string, string>>({});

  const updateMutation = useMutation({
    mutationFn: api.updateProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      queryClient.invalidateQueries({ queryKey: ['feed'] });
    },
  });

  const rerankMutation = useMutation({
    mutationFn: api.rerank,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['feed'] }),
  });

  if (!profile) return <Skeleton className="skeleton-block" />;

  const val = (key: keyof typeof profile) =>
    (form[key] as string) ??
    (Array.isArray(profile[key]) ? (profile[key] as string[]).join(', ') : String(profile[key] ?? ''));

  return (
    <>
      <div className="page-header intake-header">
        <h2>Profile & Goals</h2>
        <Link to="/profile/intake" className="btn">Full profile intake</Link>
      </div>
      <p className="intake-subtitle" style={{ marginTop: '-1rem', marginBottom: '1rem' }}>
        Quick edit below, or use full intake to build your LLM extraction pipeline.
      </p>
      <div className="detail-panel profile-form" style={{ maxWidth: 600 }}>
        <label>Long-term goals</label>
        <textarea className="form-control" value={val('long_term_goals')} onChange={(e) => setForm({ ...form, long_term_goals: e.target.value })} />
        <label>Research interests (comma-separated)</label>
        <input className="form-control" value={val('research_interests')} onChange={(e) => setForm({ ...form, research_interests: e.target.value })} />
        <label>Skills (comma-separated)</label>
        <input className="form-control" value={val('skills')} onChange={(e) => setForm({ ...form, skills: e.target.value })} />
        <label>Target regions</label>
        <input className="form-control" value={val('target_regions')} onChange={(e) => setForm({ ...form, target_regions: e.target.value })} />
        <label>Target universities</label>
        <input className="form-control" value={val('target_universities')} onChange={(e) => setForm({ ...form, target_universities: e.target.value })} />
        <label>Degree level</label>
        <input className="form-control" value={val('degree_level')} onChange={(e) => setForm({ ...form, degree_level: e.target.value })} />
        <div className="actions-row">
          <Button variant="primary" onClick={() => updateMutation.mutate({
            long_term_goals: val('long_term_goals'),
            research_interests: val('research_interests').split(',').map((s) => s.trim()).filter(Boolean),
            skills: val('skills').split(',').map((s) => s.trim()).filter(Boolean),
            target_regions: val('target_regions').split(',').map((s) => s.trim()).filter(Boolean),
            target_universities: val('target_universities').split(',').map((s) => s.trim()).filter(Boolean),
            degree_level: val('degree_level'),
          })} disabled={updateMutation.isPending}>Save & re-rank</Button>
          <Button variant="secondary" onClick={() => rerankMutation.mutate()} disabled={rerankMutation.isPending}>Re-rank only</Button>
        </div>
      </div>
    </>
  );
}
