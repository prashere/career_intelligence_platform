import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { intakeApi } from '../api/intake';
import { Button, PageHeader, Skeleton } from '../components/ui/Primitives';
import { HintPopover } from '../components/ui/HintPopover';

function StatusRow({ label, done }: { label: string; done: boolean }) {
  return (
    <div className={`status-row${done ? ' done' : ''}`}>
      <span className="status-dot" aria-hidden />
      <span>{label}</span>
      <span className="status-badge">{done ? 'Done' : 'Pending'}</span>
    </div>
  );
}

function completionPercent(status: {
  has_form_answers?: boolean;
  has_cv?: boolean;
  has_structured_profile?: boolean;
  has_compiled_artifacts?: boolean;
  has_profile_truth?: boolean;
}): number {
  const steps = [
    status.has_form_answers,
    status.has_cv,
    status.has_structured_profile,
    status.has_compiled_artifacts,
    status.has_profile_truth,
  ];
  const done = steps.filter(Boolean).length;
  return Math.round((done / steps.length) * 100);
}

export default function Profile() {
  const { data: status, isLoading } = useQuery({
    queryKey: ['intake-status'],
    queryFn: intakeApi.status,
  });

  if (isLoading) {
    return (
      <>
        <PageHeader title="Profile" />
        <Skeleton className="skeleton-block" />
      </>
    );
  }

  const hasSubmission = status?.has_form_answers ?? false;
  const pipelineReady = status?.has_structured_profile ?? false;
  const compiledReady = status?.has_compiled_artifacts ?? false;
  const percent = status ? completionPercent(status) : 0;
  const isComplete = percent === 100;

  return (
    <>
      <PageHeader
        title="Profile"
        actions={
          <Link to="/profile/setup">
            <Button variant="gold">{hasSubmission ? 'Edit setup' : 'Start setup'}</Button>
          </Link>
        }
      />

      <div className="profile-hub">
        <section className="card profile-summary-card">
          <div className="profile-summary-top">
            <div className="profile-progress-ring" style={{ '--pct': percent } as CSSProperties}>
              <span className="profile-progress-value">{percent}%</span>
            </div>
            <div>
              <h2 className="profile-summary-title">
                {isComplete ? 'Profile ready' : 'Profile in progress'}
              </h2>
              <p className="muted-text">
                {isComplete
                  ? 'Your profile is set up. Matches and alerts will use these preferences.'
                  : 'Finish setup to unlock personalized opportunity matching.'}
              </p>
              {status?.updated_at && (
                <p className="muted-text small profile-updated">
                  Last updated {new Date(status.updated_at).toLocaleString()}
                </p>
              )}
            </div>
            {!isComplete && (
              <HintPopover label="Developer setup notes">
                <ol className="hint-steps">
                  <li>Complete all sections in Profile setup and submit.</li>
                  <li>
                    Run <code>python scripts/prefill_structured.py</code> in the backend.
                  </li>
                  <li>
                    Use the CV extraction prompt, then <code>merge_profile.py</code> and{' '}
                    <code>compile_profile.py</code>.
                  </li>
                  <li>
                    Run <code>check_profile_ready.py</code>, then{' '}
                    <code>seed_sources_from_profile.py</code> and <code>sync_profile_to_db.py</code>.
                  </li>
                </ol>
              </HintPopover>
            )}
          </div>
        </section>

        <section className="card profile-status-card">
          <div className="profile-status-header">
            <h3 className="panel-title">Setup checklist</h3>
          </div>
          <div className="status-list">
            <StatusRow label="Application form" done={hasSubmission} />
            <StatusRow label="CV uploaded" done={status?.has_cv ?? false} />
            <StatusRow label="Profile structured" done={pipelineReady} />
            <StatusRow label="Matching preferences saved" done={compiledReady} />
            <StatusRow label="Summary document" done={status?.has_profile_truth ?? false} />
          </div>
        </section>

        {!isComplete && (
          <section className="card profile-cta-card">
            <h3 className="panel-title">Continue where you left off</h3>
            <p className="muted-text">
              The setup wizard walks you through your background, goals, and preferences in about ten
              minutes.
            </p>
            <Link to="/profile/setup">
              <Button variant="primary">{hasSubmission ? 'Continue setup' : 'Begin setup'}</Button>
            </Link>
          </section>
        )}
      </div>
    </>
  );
}
