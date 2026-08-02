import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { intakeApi } from '../api/intake';
import { Button, PageHeader, Skeleton } from '../components/ui/Primitives';

function StatusRow({ label, done }: { label: string; done: boolean }) {
  return (
    <div className={`status-row${done ? ' done' : ''}`}>
      <span className="status-dot" aria-hidden />
      <span>{label}</span>
      <span className="status-badge">{done ? 'Complete' : 'Pending'}</span>
    </div>
  );
}

export default function Profile() {
  const { data: status, isLoading } = useQuery({
    queryKey: ['intake-status'],
    queryFn: intakeApi.status,
  });

  if (isLoading) {
    return (
      <>
        <PageHeader eyebrow="Your profile" title="Profile" />
        <Skeleton className="skeleton-block" />
      </>
    );
  }

  const hasSubmission = status?.has_form_answers ?? false;
  const pipelineReady = status?.has_structured_profile ?? false;
  const compiledReady = status?.has_compiled_artifacts ?? false;

  return (
    <>
      <PageHeader
        eyebrow="Your profile"
        title="Profile"
        lead="Build your candidate profile once — it powers opportunity matching, filtering, and ingest sources."
        actions={
          <Link to="/profile/setup">
            <Button variant="gold">{hasSubmission ? 'Edit profile setup' : 'Start profile setup'}</Button>
          </Link>
        }
      />

      <div className="profile-hub-grid">
        <section className="card profile-status-card">
          <h3 className="panel-title">Pipeline status</h3>
          <p className="muted-text profile-status-lead">
            After submitting the form, run the backend scripts to extract CV data and compile filter rules.
          </p>
          <div className="status-list">
            <StatusRow label="Intake form submitted" done={hasSubmission} />
            <StatusRow label="CV on file" done={status?.has_cv ?? false} />
            <StatusRow label="Structured profile (L2)" done={pipelineReady} />
            <StatusRow label="Compiled artifacts (L3)" done={compiledReady} />
            <StatusRow label="Profile truth doc" done={status?.has_profile_truth ?? false} />
          </div>
          {status?.updated_at && (
            <p className="muted-text small" style={{ marginTop: '1rem' }}>
              Last saved: {new Date(status.updated_at).toLocaleString()}
            </p>
          )}
        </section>

        <section className="card profile-next-card">
          <h3 className="panel-title">Next steps</h3>
          <ol className="next-steps-list">
            <li>Complete all six sections in <strong>Profile setup</strong> and submit.</li>
            <li>Run <code>python scripts/prefill_structured.py</code> in the backend.</li>
            <li>Use the CV extraction prompt, then <code>merge_profile.py</code> and <code>compile_profile.py</code>.</li>
            <li>Run <code>check_profile_ready.py</code>, then <code>seed_sources_from_profile.py</code> and <code>sync_profile_to_db.py</code>.</li>
          </ol>
          <Link to="/profile/setup">
            <Button variant="primary">{hasSubmission ? 'Continue setup' : 'Begin setup'}</Button>
          </Link>
        </section>
      </div>
    </>
  );
}
