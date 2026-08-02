import { PageHeader, Button } from '../../components/ui/Primitives';
import { Stepper } from '../../components/form/FormControls';
import { intakeApi } from '../../api/intake';
import { useToast } from '../../components/ui/Toast';
import {
  IntakeFormData,
  IntakeSubmitResult,
  WIZARD_STEPS,
} from '../../types/intake';
import {
  StepCv,
  StepEducation,
  StepGoals,
  StepIdentity,
  StepPreferences,
  StepReview,
} from './IntakeSteps';

type WizardProps = {
  mode: 'wizard';
  step: number;
  form: IntakeFormData;
  cvText: string;
  flagshipInput: string;
  stepErrors: string[];
  isSaving: boolean;
  isSubmitting: boolean;
  onStepChange: (step: number) => void;
  onUpdate: <K extends keyof IntakeFormData>(k: K, v: IntakeFormData[K]) => void;
  onCvChange: (v: string) => void;
  onFlagshipChange: (v: string) => void;
  onBack: () => void;
  onNext: () => void;
  onSubmit: () => void;
};

type SuccessProps = {
  mode: 'success';
  submitted: IntakeSubmitResult;
  onEdit: () => void;
  onStartOver: () => void;
};

const STEP_TITLES = ['About you', 'Curriculum vitae', 'Education', 'Goals & constraints', 'Preferences', 'Review & submit'];

export function IntakeWizardView(props: WizardProps | SuccessProps) {
  const { push: toast } = useToast();

  if (props.mode === 'success') {
    return (
      <div className="intake-success">
        <div className="success-card">
          <div className="success-icon" aria-hidden>✓</div>
          <h2>You&apos;re all set</h2>
          <p>
            Your profile answers and CV have been recorded. Next we&apos;ll structure this into
            a searchable candidate profile for opportunity matching.
          </p>
          <ul className="success-next-steps">
            <li>Review your answers if anything changed</li>
            <li>We&apos;ll notify you when the next pipeline step is ready</li>
          </ul>
          <div className="success-actions">
            <Button variant="gold" onClick={props.onEdit}>Review & edit answers</Button>
            <Button variant="ghost" onClick={props.onStartOver}>Start fresh</Button>
          </div>
        </div>
      </div>
    );
  }

  const p = props;
  const handleCvFile = async (file: File) => {
    try {
      if (file.name.endsWith('.pdf')) {
        const result = await intakeApi.uploadCvFile(file);
        p.onCvChange(result.text);
        toast(`Extracted ${result.length} characters from PDF`, 'success');
      } else {
        const text = await file.text();
        p.onCvChange(text);
        await intakeApi.saveCv(text);
        toast('CV uploaded', 'success');
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Upload failed', 'error');
    }
  };

  return (
    <div className="intake-layout">
      <PageHeader
        eyebrow="Profile intake"
        title="Build your candidate profile"
        lead="Six focused steps. Your answers are saved as you go."
      />

      <div className="intake-body">
        <Stepper steps={WIZARD_STEPS} current={p.step} onStepClick={p.onStepChange} />

        <div className="intake-card">
          <h3>{STEP_TITLES[p.step]}</h3>

          {p.step === 0 && <StepIdentity form={p.form} onUpdate={p.onUpdate} />}
          {p.step === 1 && <StepCv cvText={p.cvText} onCvChange={p.onCvChange} onFile={handleCvFile} />}
          {p.step === 2 && <StepEducation form={p.form} onUpdate={p.onUpdate} />}
          {p.step === 3 && (
            <StepGoals form={p.form} flagshipInput={p.flagshipInput} onUpdate={p.onUpdate} onFlagshipChange={p.onFlagshipChange} />
          )}
          {p.step === 4 && <StepPreferences form={p.form} onUpdate={p.onUpdate} />}
          {p.step === 5 && (
            <>
              <p className="step-lead">Confirm everything looks correct, then submit.</p>
              <StepReview form={p.form} cvText={p.cvText} />
            </>
          )}

          {p.stepErrors.length > 0 && (
            <div className="step-errors" role="alert">
              <strong>Please fix the following:</strong>
              <ul>
                {p.stepErrors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          )}

          <footer className="intake-footer">
            {p.step > 0 && (
              <Button variant="ghost" onClick={p.onBack} disabled={p.isSaving}>
                Back
              </Button>
            )}
            {p.isSaving && <span className="save-indicator">Saving…</span>}
            {p.step < 5 ? (
              <Button variant="primary" onClick={p.onNext} disabled={p.isSaving}>
                Continue
              </Button>
            ) : (
              <Button variant="gold" className="btn-submit" onClick={p.onSubmit} disabled={p.isSubmitting}>
                {p.isSubmitting ? 'Submitting…' : 'Submit profile'}
              </Button>
            )}
          </footer>
        </div>
      </div>
    </div>
  );
}
