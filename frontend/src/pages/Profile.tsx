import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export default function Profile() {
  const queryClient = useQueryClient()
  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: api.profile })

  const [form, setForm] = useState<Record<string, string>>({})

  const updateMutation = useMutation({
    mutationFn: api.updateProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      queryClient.invalidateQueries({ queryKey: ['feed'] })
    },
  })

  const rerankMutation = useMutation({
    mutationFn: api.rerank,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['feed'] }),
  })

  if (!profile) return <div className="empty-state">Loading profile...</div>

  const val = (key: keyof typeof profile) => (form[key] as string) ?? (Array.isArray(profile[key]) ? (profile[key] as string[]).join(', ') : String(profile[key] ?? ''))

  const handleSave = () => {
    updateMutation.mutate({
      long_term_goals: val('long_term_goals'),
      research_interests: val('research_interests').split(',').map((s) => s.trim()).filter(Boolean),
      skills: val('skills').split(',').map((s) => s.trim()).filter(Boolean),
      target_regions: val('target_regions').split(',').map((s) => s.trim()).filter(Boolean),
      target_universities: val('target_universities').split(',').map((s) => s.trim()).filter(Boolean),
      degree_level: val('degree_level'),
    })
  }

  return (
    <>
      <div className="page-header"><h2>Profile & Goals</h2></div>
      <div className="detail-panel profile-form" style={{ maxWidth: 600 }}>
        <label>Long-term goals</label>
        <textarea value={val('long_term_goals')} onChange={(e) => setForm({ ...form, long_term_goals: e.target.value })} />

        <label>Research interests (comma-separated)</label>
        <input value={val('research_interests')} onChange={(e) => setForm({ ...form, research_interests: e.target.value })} />

        <label>Skills (comma-separated)</label>
        <input value={val('skills')} onChange={(e) => setForm({ ...form, skills: e.target.value })} />

        <label>Target regions</label>
        <input value={val('target_regions')} onChange={(e) => setForm({ ...form, target_regions: e.target.value })} />

        <label>Target universities</label>
        <input value={val('target_universities')} onChange={(e) => setForm({ ...form, target_universities: e.target.value })} />

        <label>Degree level</label>
        <input value={val('degree_level')} onChange={(e) => setForm({ ...form, degree_level: e.target.value })} />

        <div className="actions-row">
          <button className="btn" onClick={handleSave} disabled={updateMutation.isPending}>Save & re-rank</button>
          <button className="btn btn-secondary" onClick={() => rerankMutation.mutate()} disabled={rerankMutation.isPending}>Re-rank only</button>
        </div>
      </div>
    </>
  )
}
