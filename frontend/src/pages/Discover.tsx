import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Button, PageHeader } from '../components/ui/Primitives';

export default function Discover() {
  const queryClient = useQueryClient();
  const [personName, setPersonName] = useState('');
  const [communityName, setCommunityName] = useState('');

  const { data: people } = useQuery({ queryKey: ['people'], queryFn: api.people });
  const { data: communities } = useQuery({ queryKey: ['communities'], queryFn: api.communities });
  const { data: experiences } = useQuery({ queryKey: ['experiences'], queryFn: api.experiences });

  const addPerson = useMutation({
    mutationFn: api.createPerson,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['people'] });
      setPersonName('');
    },
  });

  const addCommunity = useMutation({
    mutationFn: api.createCommunity,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['communities'] });
      setCommunityName('');
    },
  });

  return (
    <>
      <PageHeader eyebrow="Connect" title="Network" lead="Researchers, communities, and experiences worth remembering." />

      <div className="dashboard-grid">
        <section className="card dashboard-panel">
          <h3 className="panel-title">People</h3>
          <div className="filter-bar compact">
            <input className="form-control" placeholder="Add researcher or mentor…" value={personName} onChange={(e) => setPersonName(e.target.value)} />
            <Button variant="primary" onClick={() => personName && addPerson.mutate({ name: personName, role: 'researcher' })}>Add</Button>
          </div>
          {people?.map((p) => (
            <div key={p.id} className="notification-item">
              <strong>{p.name}</strong>
              <p className="muted-text">{p.role}{p.affiliation ? ` · ${p.affiliation}` : ''}</p>
              {p.research_areas?.length > 0 && <p className="muted-text small">{p.research_areas.join(', ')}</p>}
            </div>
          ))}
        </section>

        <section className="card dashboard-panel">
          <h3 className="panel-title">Communities</h3>
          <div className="filter-bar compact">
            <input className="form-control" placeholder="Add community…" value={communityName} onChange={(e) => setCommunityName(e.target.value)} />
            <Button variant="primary" onClick={() => communityName && addCommunity.mutate({ name: communityName, community_type: 'forum' })}>Add</Button>
          </div>
          {communities?.map((c) => (
            <div key={c.id} className="notification-item">
              <strong>{c.name}</strong>
              <p className="muted-text">{c.community_type}</p>
            </div>
          ))}
        </section>

        <section className="card dashboard-panel">
          <h3 className="panel-title">Experience log</h3>
          {experiences?.map((e) => (
            <div key={e.id} className="notification-item">
              <strong>{e.title}</strong>
              <p className="muted-text">{e.experience_type} · {e.status}</p>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}
