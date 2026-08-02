import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Badge, Button, PageHeader, Skeleton } from '../components/ui/Primitives';

export default function Detail() {
  const { id } = useParams<{ id: string }>();
  const [message, setMessage] = useState('');
  const [chatHistory, setChatHistory] = useState<{ role: string; content: string }[]>([]);
  const [useAgent, setUseAgent] = useState(true);
  const queryClient = useQueryClient();

  const { data: opp, isLoading } = useQuery({
    queryKey: ['opportunity', id],
    queryFn: () => api.opportunity(id!),
    enabled: !!id,
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => api.updateStatus(id!, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['opportunity', id] }),
  });

  const chatMutation = useMutation({
    mutationFn: (msg: string) => (useAgent ? api.agentChat(id!, msg) : api.chat(id!, msg)),
    onSuccess: (data) => {
      setChatHistory((h) => [...h, { role: 'assistant', content: data.reply }]);
    },
  });

  const handleSend = () => {
    if (!message.trim()) return;
    setChatHistory((h) => [...h, { role: 'user', content: message }]);
    chatMutation.mutate(message);
    setMessage('');
  };

  if (isLoading || !opp) {
    return (
      <>
        <Skeleton className="skeleton-title" />
        <Skeleton className="skeleton-block" />
      </>
    );
  }

  return (
    <>
      <Link to="/" className="back-link">← Back to opportunities</Link>

      <PageHeader
        title={opp.title}
        lead={[opp.institution, opp.program].filter(Boolean).join(' · ')}
      />

      <div className="detail-layout">
        <div className="card detail-main">
          <div className="detail-badges">
            {opp.fit_level && <Badge variant={opp.fit_level === 'strong' ? 'success' : 'gold'}>{opp.fit_level} fit</Badge>}
            {opp.opportunity_type && <Badge variant="navy">{opp.opportunity_type}</Badge>}
            {opp.urgency_label && <Badge variant="warning">{opp.urgency_label}</Badge>}
          </div>

          {opp.fit_explanation && (
            <div className="fit-panel">
              <h4>Why this matches you</h4>
              <p>{opp.fit_explanation}</p>
              {opp.fit_score != null && <span className="fit-score-label">{Math.round(opp.fit_score)}% profile match</span>}
            </div>
          )}

          <h4 className="panel-title">Requirements</h4>
          <ul className="requirements-list">
            {(opp.requirements.length ? opp.requirements : ['No requirements listed yet']).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>

          <div className="detail-actions">
            <Button variant="gold" onClick={() => statusMutation.mutate('in_progress')}>Start applying</Button>
            <Button variant="secondary" onClick={() => statusMutation.mutate('saved')}>Save for later</Button>
            <a className="btn btn-ghost" href={opp.url} target="_blank" rel="noreferrer">Official page ↗</a>
            <a className="btn btn-ghost" href={api.calendarUrl(opp.id)} download>Add to calendar</a>
          </div>
        </div>

        <div className="card chat-panel">
          <div className="chat-header">
            <h3 className="panel-title">Research assistant</h3>
            <label className="toggle-field">
              <input type="checkbox" checked={useAgent} onChange={(e) => setUseAgent(e.target.checked)} />
              <span>Deep research mode</span>
            </label>
          </div>
          <p className="muted-text chat-hint">Ask about eligibility, competitiveness, or application strategy.</p>

          <div className="chat-messages">
            {chatHistory.length === 0 && (
              <div className="chat-msg assistant chat-placeholder">
                Try: &ldquo;Am I competitive for this as an international MSc applicant?&rdquo;
              </div>
            )}
            {chatHistory.map((msg, i) => (
              <div key={i} className={`chat-msg ${msg.role}`}>{msg.content}</div>
            ))}
            {chatMutation.isPending && <div className="chat-msg assistant">Thinking…</div>}
          </div>

          <div className="chat-input-row">
            <input
              className="form-control"
              placeholder="Ask a question…"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            />
            <Button variant="primary" onClick={handleSend} disabled={chatMutation.isPending}>Send</Button>
          </div>
        </div>
      </div>
    </>
  );
}
