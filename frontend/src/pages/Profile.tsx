import type { CSSProperties } from 'react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { intakeApi } from '../api/intake';
import {
  findStuckStep,
  pipelinePercent,
  ProfilePipelinePanel,
  stepLabel,
} from '../components/profile/ProfilePipelinePanel';
import { StructuredProfileView } from '../components/profile/StructuredProfileView';
import { Button, PageHeader, Skeleton } from '../components/ui/Primitives';
import { Modal } from '../components/ui/Modal';
import { useToast } from '../components/ui/Toast';

function StatusRow({ label, done }: { label: string; done: boolean }) {
  return (
    <div className={`status-row${done ? ' done' : ''}`}>
      <span className="status-dot" aria-hidden />
      <span>{label}</span>
      <span className="status-badge">{done ? 'Done' : 'Pending'}</span>
    </div>
  );
}

export default function Profile() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { push: toast } = useToast();
  const [errorModal, setErrorModal] = useState<string | null>(null);
  const lastAlertKeyRef = useRef<string | null>(null);

  const pipelineActive = (status?: string) => status === 'queued' || status === 'running';

  const { data: status, isLoading } = useQuery({
    queryKey: ['intake-status'],
    queryFn: intakeApi.status,
    refetchInterval: (query) => {
      const pipeStatus = query.state.data?.pipeline?.status;
      const ingest = query.state.data?.pipeline?.steps?.find((s) => s.name === 'ingest');
      const ingestActive =
        ingest?.status === 'pending' || ingest?.status === 'running';
      return pipelineActive(pipeStatus) || ingestActive ? 2500 : false;
    },
  });

  const hasSubmission = status?.has_form_answers ?? false;
  const pipeline = status?.pipeline;
  const ingestStep = pipeline?.steps?.find((s) => s.name === 'ingest');
  const ingestActive =
    ingestStep?.status === 'pending' || ingestStep?.status === 'running';
  const pipelineRunning =
    pipelineActive(pipeline?.status) || ingestActive;
  const pipelineFailed = pipeline?.status === 'failed';
  const ingestFailed = ingestStep?.status === 'failed';
  const pipelineComplete =
    pipeline?.status === 'completed' ||
    (status?.has_structured_profile && status?.has_compiled_artifacts);
  const percent = pipeline
    ? pipelinePercent(pipeline.steps)
    : pipelineComplete
      ? 100
      : hasSubmission
        ? 15
        : 0;
  const isComplete = pipelineComplete && !pipelineRunning && !ingestFailed;
  const hasProfileData =
    hasSubmission || status?.has_structured_profile || status?.has_draft;

  const { data: structuredProfile } = useQuery({
    queryKey: ['structured-profile'],
    queryFn: intakeApi.getStructuredProfile,
    enabled: Boolean(status?.has_structured_profile),
    retry: false,
  });

  const retryMutation = useMutation({
    mutationFn: intakeApi.retryPipeline,
    onSuccess: () => {
      lastAlertKeyRef.current = null;
      queryClient.invalidateQueries({ queryKey: ['intake-status'] });
      toast('Processing restarted', 'info');
    },
    onError: (err: Error) => toast(err.message, 'error'),
  });

  const deleteMutation = useMutation({
    mutationFn: intakeApi.deleteProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['intake-status'] });
      queryClient.invalidateQueries({ queryKey: ['intake-draft'] });
      queryClient.invalidateQueries({ queryKey: ['structured-profile'] });
      setErrorModal(null);
      lastAlertKeyRef.current = null;
      toast('Profile deleted. Fill out a new setup form to start over', 'success');
      navigate('/profile/setup');
    },
    onError: (err: Error) => toast(err.message, 'error'),
  });

  useEffect(() => {
    if (!pipeline) return;

    const failedStep = pipeline.steps?.find((s) => s.status === 'failed');
    const stuckStep = findStuckStep(pipeline.steps ?? []);
    let message: string | null = null;
    let alertKey: string | null = null;

    if (pipelineFailed || ingestFailed) {
      message =
        pipeline.error ??
        failedStep?.error ??
        ingestStep?.error ??
        'Profile processing failed. Check the step logs below and retry.';
      alertKey = `failed-${pipeline.id}-${failedStep?.name ?? 'run'}`;
    } else if (stuckStep) {
      message = `Step "${stepLabel(stuckStep.name)}" has been running for over 8 minutes. The worker may be stuck. Try retrying or contact support if this persists.`;
      alertKey = `stuck-${pipeline.id}-${stuckStep.name}`;
    }

    if (message && alertKey !== lastAlertKeyRef.current) {
      lastAlertKeyRef.current = alertKey;
      setErrorModal(message);
    }
  }, [pipeline, pipelineFailed, ingestFailed, ingestStep]);

  const handleDelete = () => {
    if (
      window.confirm(
        'Delete your entire profile, form answers, and processing history? You can fill out a new setup form from scratch.',
      )
    ) {
      deleteMutation.mutate();
    }
  };

  if (isLoading) {
    return (
      <>
        <PageHeader title="Profile" />
        <Skeleton className="skeleton-block" />
      </>
    );
  }

  const showPipelinePanel =
    pipeline?.steps?.length > 0 &&
    (pipelineRunning || pipelineFailed || ingestFailed || hasSubmission);

  return (
    <>
      {errorModal && (
        <Modal
          title="Profile processing issue"
          variant="error"
          onClose={() => setErrorModal(null)}
          actions={
            <>
              {(pipelineFailed || ingestFailed) && (
                <Button
                  variant="primary"
                  onClick={() => {
                    setErrorModal(null);
                    retryMutation.mutate();
                  }}
                  disabled={retryMutation.isPending}
                >
                  {retryMutation.isPending ? 'Retrying…' : 'Retry processing'}
                </Button>
              )}
              <Button variant="ghost" onClick={() => setErrorModal(null)}>Close</Button>
            </>
          }
        >
          <p>{errorModal}</p>
        </Modal>
      )}

      <PageHeader
        title="Profile"
        actions={
          <div className="page-header-actions">
            {hasProfileData && (
              <Button
                variant="ghost"
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? 'Deleting…' : 'Delete profile'}
              </Button>
            )}
            <Link to="/profile/setup">
              <Button variant="gold">
                {hasProfileData ? 'Fill new form' : 'Start setup'}
              </Button>
            </Link>
          </div>
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
                {pipelineRunning
                  ? 'Processing your profile'
                  : pipelineFailed || ingestFailed
                    ? 'Profile processing failed'
                    : isComplete
                      ? 'Profile ready'
                      : 'Profile in progress'}
              </h2>
              <p className="muted-text">
                {pipelineRunning
                  ? 'We are building your profile and starting opportunity discovery. Step logs update live below.'
                  : pipelineFailed || ingestFailed
                    ? 'Something went wrong. Review the logs for the failed step, then retry.'
                    : isComplete
                      ? 'Your profile is set up. Review your final profile below.'
                      : 'Finish setup to unlock personalized opportunity matching.'}
              </p>
              {status?.updated_at && (
                <p className="muted-text small profile-updated">
                  Last updated {new Date(status.updated_at).toLocaleString()}
                </p>
              )}
            </div>
          </div>

          {showPipelinePanel && (
            <div className="pipeline-stepper-wrap">
              <h3 className="panel-title pipeline-logs-title">Processing steps</h3>
              <ProfilePipelinePanel steps={pipeline.steps} />
            </div>
          )}

          {pipelineRunning && ingestActive && pipeline?.status === 'completed' && (
            <p className="muted-text small pipeline-ingest-note">
              Discovering and ranking opportunities in the background…
            </p>
          )}

          {(pipelineFailed || ingestFailed) && (
            <div className="pipeline-retry-row">
              <Button
                variant="primary"
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
              >
                {retryMutation.isPending ? 'Retrying…' : 'Retry processing'}
              </Button>
            </div>
          )}
        </section>

        {isComplete && structuredProfile && (
          <section className="card profile-status-card">
            <h3 className="panel-title">Your profile</h3>
            <p className="muted-text small profile-view-lead">
              This is the structured profile we use for matching, filtering, and ranking opportunities.
            </p>
            <StructuredProfileView data={structuredProfile} />
            <div className="profile-complete-links">
              <Link to="/">
                <Button variant="primary">Go to dashboard</Button>
              </Link>
            </div>
          </section>
        )}

        {isComplete && status?.summary && !structuredProfile && (
          <section className="card profile-status-card">
            <h3 className="panel-title">Selected sources</h3>
            {status.summary.aggregator_names?.length ? (
              <div className="source-chip-row">
                {status.summary.aggregator_names.map((name) => (
                  <span key={name} className="source-chip">{name}</span>
                ))}
              </div>
            ) : (
              <p className="muted-text">No aggregators selected.</p>
            )}
            {status.summary.discovery_mode && (
              <p className="muted-text small">
                Discovery mode: {status.summary.discovery_mode.replace('_', ' ')}
              </p>
            )}
            {status.summary.profile_truth_excerpt && (
              <details className="profile-truth-details">
                <summary>Profile summary</summary>
                <p className="profile-truth-excerpt">{status.summary.profile_truth_excerpt}</p>
              </details>
            )}
          </section>
        )}

        <section className="card profile-status-card">
          <div className="profile-status-header">
            <h3 className="panel-title">Setup checklist</h3>
          </div>
          <div className="status-list">
            <StatusRow label="Application form" done={hasSubmission} />
            <StatusRow label="CV uploaded" done={status?.has_cv ?? false} />
            <StatusRow
              label={pipelineRunning ? 'Processing profile' : 'Profile structured'}
              done={status?.has_structured_profile ?? false}
            />
            <StatusRow label="Matching preferences saved" done={status?.has_compiled_artifacts ?? false} />
            <StatusRow label="Summary document" done={status?.has_profile_truth ?? false} />
          </div>
        </section>

        {!isComplete && !pipelineRunning && !hasSubmission && (
          <section className="card profile-cta-card">
            <h3 className="panel-title">Get started</h3>
            <p className="muted-text">
              The setup wizard walks you through your background, goals, and preferences in about ten
              minutes.
            </p>
            <Link to="/profile/setup">
              <Button variant="primary">Begin setup</Button>
            </Link>
          </section>
        )}
      </div>
    </>
  );
}
