import { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { intakeApi } from '../../api/intake';
import { useToast } from '../../components/ui/Toast';
import {
  DEFAULT_INTAKE_FORM,
  IntakeFormData,
  IntakeSubmitResult,
  WIZARD_STEPS,
  mergeForm,
} from '../../types/intake';
import { getStepErrors } from './validation';
import { IntakeWizardView } from './IntakeWizardView';

export function IntakeWizard() {
  const queryClient = useQueryClient();
  const { push: toast } = useToast();
  const { data: draft, isLoading } = useQuery({
    queryKey: ['intake-draft'],
    queryFn: intakeApi.getDraft,
  });

  const [step, setStep] = useState(0);
  const [form, setForm] = useState<IntakeFormData>(DEFAULT_INTAKE_FORM);
  const [cvText, setCvText] = useState('');
  const [flagshipInput, setFlagshipInput] = useState('');
  const [submitted, setSubmitted] = useState<IntakeSubmitResult | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);
  const [stepErrors, setStepErrors] = useState<string[]>([]);

  useEffect(() => {
    if (draft) {
      setStep(Math.min(draft.step ?? 0, WIZARD_STEPS.length - 1));
      const merged = mergeForm(draft.form as Partial<IntakeFormData>);
      setForm(merged);
      setCvText(draft.cv_text ?? '');
      setFlagshipInput(merged.flagship_projects.join(', '));
    }
  }, [draft]);

  const saveDraftMutation = useMutation({
    mutationFn: ({ s, f, cv }: { s: number; f: IntakeFormData; cv: string }) =>
      intakeApi.saveDraft(s, f, cv),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['intake-draft'] });
      toast('Draft saved', 'success');
    },
  });

  const submitMutation = useMutation({
    mutationFn: (payload: { form: IntakeFormData; cv: string }) =>
      intakeApi.submit(payload.form, payload.cv),
    onSuccess: (data) => {
      setSubmitted(data);
      setShowSuccess(true);
      toast('Profile submitted successfully', 'success');
      queryClient.invalidateQueries({ queryKey: ['intake-status'] });
    },
    onError: (err: Error) => toast(err.message, 'error'),
  });

  const preparedForm = useCallback((): IntakeFormData => {
    return {
      ...form,
      flagship_projects: flagshipInput.split(/[,;]/).map((s) => s.trim()).filter(Boolean),
    };
  }, [form, flagshipInput]);

  const persist = useCallback(
    async (nextStep: number, silent = false) => {
      const f = preparedForm();
      if (!silent) {
        await saveDraftMutation.mutateAsync({ s: nextStep, f, cv: cvText });
      } else {
        await intakeApi.saveDraft(nextStep, f, cvText);
      }
      setForm(f);
      setStep(nextStep);
      setStepErrors([]);
    },
    [preparedForm, cvText, saveDraftMutation],
  );

  const tryNext = async () => {
    const f = preparedForm();
    const errors = getStepErrors(step, f, cvText);
    if (errors.length) {
      setStepErrors(errors);
      return;
    }
    await persist(step + 1);
  };

  const trySubmit = () => {
    const f = preparedForm();
    const errors = [
      ...getStepErrors(0, f, cvText),
      ...getStepErrors(2, f, cvText),
      ...getStepErrors(3, f, cvText),
    ];
    if (cvText.trim().length < 100) errors.push('CV text is too short');
    if (errors.length) {
      setStepErrors([...new Set(errors)]);
      return;
    }
    submitMutation.mutate({ form: f, cv: cvText });
  };

  const update = <K extends keyof IntakeFormData>(key: K, value: IntakeFormData[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setStepErrors([]);
  };

  if (isLoading) {
    return (
      <div className="intake-loading">
        <div className="skeleton skeleton-title" />
        <div className="skeleton skeleton-block" />
      </div>
    );
  }

  if (showSuccess && submitted) {
    return (
      <IntakeWizardView
        mode="success"
        submitted={submitted}
        onEdit={() => {
          setShowSuccess(false);
          setStep(5);
        }}
        onStartOver={() => {
          setShowSuccess(false);
          setSubmitted(null);
          setStep(0);
        }}
      />
    );
  }

  return (
    <IntakeWizardView
      mode="wizard"
      step={step}
      form={preparedForm()}
      cvText={cvText}
      flagshipInput={flagshipInput}
      stepErrors={stepErrors}
      isSaving={saveDraftMutation.isPending}
      isSubmitting={submitMutation.isPending}
      onStepChange={(s) => s <= step && void persist(s, true)}
      onUpdate={update}
      onCvChange={setCvText}
      onFlagshipChange={(v) => {
        setFlagshipInput(v);
        setStepErrors([]);
      }}
      onBack={() => step > 0 && void persist(step - 1, true)}
      onNext={() => void tryNext()}
      onSubmit={trySubmit}
    />
  );
}
