import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { intakeApi } from '../api/intake';
import { COUNTRIES, countryNameByCode } from '../data/countries';
import {
  DEGREE_LEVELS,
  DISCOVERY_MODE_OPTIONS,
  ENGLISH_TESTS,
  FELLOWSHIP_TYPES,
  FUNDING_REQUIREMENT_OPTIONS,
  GPA_SCALES,
  HONORS_OPTIONS,
  INTAKE_TERMS,
  MONTHS,
  OTHER_LANGUAGE_OPTIONS,
  PRIORITY_COUNTRY_CHIPS,
  PROGRAM_STYLE_OPTIONS,
  SEARCH_SOURCE_OPTIONS,
  STUDY_FIELDS,
  STUDY_YEARS,
  graduationYears,
} from '../data/form-options';
import {
  ChipGroup,
  CountryCombobox,
  FileDropZone,
  FormField,
  FormRow,
  FormSection,
  HorizontalStepper,
  ReviewBlock,
  SelectInput,
  useFieldId,
} from '../components/form/FormControls';
import { Button, PageHeader } from '../components/ui/Primitives';
import { useToast } from '../components/ui/Toast';
import {
  ANTI_GOAL_OPTIONS,
  AntiGoalKey,
  DEFAULT_INTAKE_FORM,
  FIELD_SUGGESTIONS,
  FORM_STEPS,
  IntakeFormData,
  REGION_OPTIONS,
  chipsToInput,
  collapseFundingRequirement,
  collapseProgramStyle,
  mergeForm,
  normalizeDraftForm,
  parseChipInput,
  prepareFormPayload,
} from '../types/intake';

function setField<K extends keyof IntakeFormData>(
  form: IntakeFormData,
  key: K,
  value: IntakeFormData[K],
): IntakeFormData {
  return { ...form, [key]: value };
}

export default function ProfileIntake() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { push: toast } = useToast();
  const nameId = useFieldId('name');
  const emailId = useFieldId('email');
  const cvId = useFieldId('cv');

  const { data: draft, isLoading } = useQuery({
    queryKey: ['intake-draft'],
    queryFn: intakeApi.getDraft,
  });

  const [step, setStep] = useState(0);
  const [form, setForm] = useState<IntakeFormData>(DEFAULT_INTAKE_FORM);
  const [cvText, setCvText] = useState('');
  const [cvUploading, setCvUploading] = useState(false);
  const [cvFilename, setCvFilename] = useState<string | null>(null);
  const [fieldsInput, setFieldsInput] = useState('');
  const [regionsInput, setRegionsInput] = useState('');
  const [countriesInput, setCountriesInput] = useState('');

  useEffect(() => {
    if (draft?.form && Object.keys(draft.form).length > 0) {
      setStep(draft.step ?? 0);
      const normalized = normalizeDraftForm(draft.form as Partial<IntakeFormData> & Record<string, unknown>);
      setForm(normalized);
      setCvText(draft.cv_text ?? '');
      setFieldsInput(chipsToInput(normalized.target_fields));
      setRegionsInput(chipsToInput(normalized.target_regions));
      setCountriesInput(chipsToInput(normalized.target_countries_priority));
    }
  }, [draft]);

  const withChips = useCallback(
    (f: IntakeFormData): IntakeFormData =>
      setField(
        setField(
          setField(f, 'target_fields', parseChipInput(fieldsInput)),
          'target_regions',
          parseChipInput(regionsInput),
        ),
        'target_countries_priority',
        parseChipInput(countriesInput),
      ),
    [fieldsInput, regionsInput, countriesInput],
  );

  const toPayload = useCallback(
    (f: IntakeFormData) => prepareFormPayload(withChips(f), countryNameByCode),
    [withChips],
  );

  const { data: intakeStatus } = useQuery({
    queryKey: ['intake-status'],
    queryFn: intakeApi.status,
  });

  const hasExistingProfile =
    intakeStatus?.has_structured_profile || intakeStatus?.has_form_answers;

  const deleteMutation = useMutation({
    mutationFn: intakeApi.deleteProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['intake-draft'] });
      queryClient.invalidateQueries({ queryKey: ['intake-status'] });
      setForm(DEFAULT_INTAKE_FORM);
      setCvText('');
      setCvFilename(null);
      setFieldsInput('');
      setRegionsInput('');
      setCountriesInput('');
      setStep(0);
      toast('Profile deleted — you can start fresh', 'success');
    },
    onError: (err: Error) => toast(err.message, 'error'),
  });

  const saveDraftMutation = useMutation({
    mutationFn: ({ s, f, cv }: { s: number; f: IntakeFormData; cv: string }) =>
      intakeApi.saveDraft(s, toPayload(f), cv),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['intake-draft'] }),
  });

  const submitMutation = useMutation({
    mutationFn: ({ s, f, cv }: { s: number; f: IntakeFormData; cv: string }) =>
      intakeApi.submit(s, toPayload(f), cv),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['intake-status'] });
      toast('Profile submitted — processing started', 'success');
      navigate('/profile');
    },
    onError: (err: Error) => toast(err.message, 'error'),
  });

  const persist = useCallback(
    async (nextStep: number, nextForm: IntakeFormData, nextCv: string) => {
      const merged = withChips(nextForm);
      await saveDraftMutation.mutateAsync({ s: nextStep, f: merged, cv: nextCv });
      setForm(merged);
      setStep(nextStep);
    },
    [saveDraftMutation, withChips],
  );

  const update = <K extends keyof IntakeFormData>(key: K, value: IntakeFormData[K]) => {
    setForm((prev) => setField(prev, key, value));
  };

  const toggleAntiGoal = (key: AntiGoalKey) => {
    const current = form.anti_goals;
    update(
      'anti_goals',
      current.includes(key) ? current.filter((k) => k !== key) : [...current, key],
    );
  };

  const toggleProgramStyle = (value: string) => {
    const current = form.program_styles;
    if (value === 'no_preference') {
      update('program_styles', current.includes('no_preference') ? [] : ['no_preference']);
      return;
    }
    let next = current.includes(value)
      ? current.filter((x) => x !== value)
      : [...current.filter((x) => x !== 'no_preference'), value];
    if (!next.length) {
      next = ['no_preference'];
    }
    update('program_styles', next);
  };

  const toggleFundingRequirement = (value: string) => {
    const current = form.funding_requirements;
    const next = current.includes(value)
      ? current.filter((x) => x !== value)
      : [...current, value];
    update('funding_requirements', next.length ? next : [value]);
  };

  const toggleChipList = (key: 'search_sources' | 'other_languages', value: string) => {
    const current = form[key];
    update(
      key,
      current.includes(value) ? current.filter((x) => x !== value) : [...current, value],
    );
  };

  const programStyleReview = () => {
    const labels = form.program_styles
      .map((v) => PROGRAM_STYLE_OPTIONS.find((o) => o.value === v)?.label ?? v)
      .join(' · ');
    const collapsed = collapseProgramStyle(form.program_styles);
    if (!labels) return collapsed.replace(/_/g, ' ');
    if (collapsed === 'no_preference' && form.program_styles.length > 1) {
      return `${labels} (open to both styles)`;
    }
    return labels;
  };

  const fundingReview = () => {
    const labels = form.funding_requirements
      .map((v) => FUNDING_REQUIREMENT_OPTIONS.find((o) => o.value === v)?.label ?? v)
      .join(' · ');
    const collapsed = collapseFundingRequirement(form.funding_requirements);
    const collapsedLabel =
      FUNDING_REQUIREMENT_OPTIONS.find((o) => o.value === collapsed)?.label ??
      collapsed.replace(/_/g, ' ');
    if (form.funding_requirements.length > 1) {
      return `${labels} (filter: ${collapsedLabel})`;
    }
    return labels || collapsedLabel;
  };

  const resolvedIntakeTerm = () =>
    form.target_intake_term === 'custom' ? form.custom_intake_term : form.target_intake_term;

  const resolvedField = () =>
    form.field_of_study === 'Other' ? form.field_of_study_other : form.field_of_study;

  const canNext = (): boolean => {
    switch (step) {
      case 0:
        return !!(
          form.full_name.trim() &&
          form.nationality_code &&
          form.linkedin_url.trim()
        );
      case 1:
        return cvText.trim().length > 100;
      case 2:
        return !!(
          form.degree_level &&
          resolvedField().trim() &&
          form.institution.trim()
        );
      case 3:
        return !!(
          resolvedIntakeTerm().trim() &&
          form.funding_requirements.length >= 1 &&
          parseChipInput(regionsInput).length >= 1 &&
          parseChipInput(fieldsInput).length >= 3
        );
      case 4:
        if (form.discovery_mode === 'target_list') {
          return form.target_universities.trim().length > 0;
        }
        return true;
      default:
        return true;
    }
  };

  const goNext = async () => {
    if (!canNext()) return;
    if (step === FORM_STEPS.length - 1) {
      submitMutation.mutate({ s: step, f: form, cv: cvText });
      return;
    }
    await persist(step + 1, form, cvText);
  };

  const goBack = async () => {
    if (step > 0) await persist(step - 1, form, cvText);
  };

  const handleCvFile = async (file: File) => {
    setCvUploading(true);
    try {
      const lower = file.name.toLowerCase();
      if (lower.endsWith('.pdf') || lower.endsWith('.txt')) {
        const result = await intakeApi.uploadCvFile(file);
        setCvText(result.text);
        setCvFilename(result.filename);
        toast(`Extracted ${result.length.toLocaleString()} characters from ${result.filename}`, 'success');
      } else {
        const text = await file.text();
        setCvText(text);
        setCvFilename(file.name);
        await intakeApi.saveCv(text);
        toast(`Loaded ${text.length.toLocaleString()} characters`, 'success');
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : 'CV upload failed', 'error');
    } finally {
      setCvUploading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="empty-state card">
        <p className="muted-text">Loading your draft…</p>
      </div>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Profile setup"
        title={FORM_STEPS[step]?.label ?? 'Setup'}
        lead="Six short sections, about 10 minutes. Tell us about yourself, we'll match you to funded opportunities."
        actions={
          <div className="page-header-actions">
            {hasExistingProfile && (
              <button
                type="button"
                className="btn-icon-delete"
                aria-label="Delete profile and start over"
                title="Delete profile and start over"
                disabled={deleteMutation.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      'Delete your profile and all saved answers? You can fill out a new setup from scratch.',
                    )
                  ) {
                    deleteMutation.mutate();
                  }
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path
                    d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14Z"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path d="M10 11v6M14 11v6" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
                </svg>
              </button>
            )}
            <Link to="/profile">
              <Button variant="ghost">Back to profile</Button>
            </Link>
          </div>
        }
      />

      <HorizontalStepper steps={FORM_STEPS} current={step} />

      <div className="card intake-form-card">
        {step === 0 && (
          <FormSection title="About you" description="Identity and links used for eligibility and your profile truth document.">
            <FormRow>
              <FormField label="Full name" required htmlFor={nameId}>
                <input id={nameId} className="form-control" value={form.full_name} onChange={(e) => update('full_name', e.target.value)} autoComplete="name" />
              </FormField>
              <FormField label="Email" htmlFor={emailId} hint="Optional, for reminders later">
                <input id={emailId} type="email" className="form-control" value={form.email} onChange={(e) => update('email', e.target.value)} autoComplete="email" />
              </FormField>
            </FormRow>
            <FormRow>
              <FormField label="Nationality" required hint="Country of citizenship">
                <CountryCombobox
                  value={form.nationality_code}
                  onChange={(code) => update('nationality_code', code)}
                  countries={COUNTRIES}
                  placeholder="Search nationality…"
                />
              </FormField>
              <FormField label="Current country" hint="Where you live now">
                <CountryCombobox
                  value={form.current_country_code}
                  onChange={(code) => update('current_country_code', code)}
                  countries={COUNTRIES}
                  placeholder="Search country…"
                />
              </FormField>
            </FormRow>
            <FormField label="LinkedIn URL" required>
              <input className="form-control" value={form.linkedin_url} onChange={(e) => update('linkedin_url', e.target.value)} placeholder="https://linkedin.com/in/…" />
            </FormField>
            <FormRow>
              <FormField label="GitHub URL">
                <input className="form-control" value={form.github_url} onChange={(e) => update('github_url', e.target.value)} placeholder="https://github.com/…" />
              </FormField>
              <FormField label="Portfolio / website">
                <input className="form-control" value={form.website_url} onChange={(e) => update('website_url', e.target.value)} />
              </FormField>
            </FormRow>
            <FormRow>
              <FormField label="Google Scholar">
                <input className="form-control" value={form.google_scholar_url} onChange={(e) => update('google_scholar_url', e.target.value)} />
              </FormField>
              <FormField label="ORCID">
                <input className="form-control" value={form.orcid} onChange={(e) => update('orcid', e.target.value)} placeholder="0000-0000-0000-0000" />
              </FormField>
            </FormRow>
          </FormSection>
        )}

        {step === 1 && (
          <FormSection title="Curriculum vitae" description="Upload your CV as PDF, we extract the text automatically. You can edit the result below.">
            <FileDropZone
              accept=".pdf,.txt,application/pdf,text/plain"
              label={cvUploading ? 'Extracting text…' : 'Drop CV here or click to upload'}
              hint="PDF or plain text · max 10 MB"
              onFile={handleCvFile}
            />
            {cvFilename && (
              <p className="field-hint cv-file-meta">
                Loaded from: <strong>{cvFilename}</strong>
              </p>
            )}
            <FormField label="CV text" required htmlFor={cvId} hint="Review and edit extracted text if needed">
              <textarea
                id={cvId}
                className="form-control cv-textarea"
                value={cvText}
                onChange={(e) => setCvText(e.target.value)}
                placeholder="Upload a PDF above, or paste CV text here…"
                rows={14}
                disabled={cvUploading}
              />
            </FormField>
            <p className="field-hint">
              {cvText.length.toLocaleString()} characters
              {cvText.length < 100 ? ' · need at least 100' : ''}
            </p>
          </FormSection>
        )}

        {step === 2 && (
          <FormSection title="Education & language" description="Pre-fill what you know, CV extraction fills in remaining details.">
            <FormRow>
              <FormField label="Highest degree" required>
                <SelectInput
                  value={form.degree_level}
                  onChange={(v) => update('degree_level', v)}
                  options={DEGREE_LEVELS}
                  placeholder="Select degree level"
                />
              </FormField>
              <FormField label="Field of study" required>
                <SelectInput
                  value={form.field_of_study}
                  onChange={(v) => update('field_of_study', v)}
                  options={STUDY_FIELDS}
                  placeholder="Select field"
                />
              </FormField>
            </FormRow>
            {form.field_of_study === 'Other' && (
              <FormField label="Field of study (other)">
                <input className="form-control" value={form.field_of_study_other} onChange={(e) => update('field_of_study_other', e.target.value)} />
              </FormField>
            )}
            <FormField label="Institution" required>
              <input className="form-control" value={form.institution} onChange={(e) => update('institution', e.target.value)} />
            </FormField>
            <FormRow>
              <FormField label="Graduation month">
                <SelectInput value={form.graduation_month} onChange={(v) => update('graduation_month', v)} options={MONTHS} placeholder="Month" />
              </FormField>
              <FormField label="Graduation year">
                <SelectInput
                  value={form.graduation_year}
                  onChange={(v) => update('graduation_year', String(v))}
                  options={graduationYears().map(String)}
                  placeholder="Year"
                />
              </FormField>
            </FormRow>
            <FormRow>
              <FormField label="GPA / grade">
                <input className="form-control" value={form.gpa} onChange={(e) => update('gpa', e.target.value)} placeholder="e.g. 82.11" />
              </FormField>
              <FormField label="GPA scale">
                <SelectInput value={form.gpa_scale} onChange={(v) => update('gpa_scale', v)} options={GPA_SCALES} />
              </FormField>
            </FormRow>
            <FormField label="Honors / classification">
              <SelectInput value={form.honors} onChange={(v) => update('honors', v)} options={HONORS_OPTIONS} placeholder="Select if applicable" />
            </FormField>
            {form.honors === 'other' && (
              <FormField label="Honors (other)">
                <input className="form-control" value={form.honors_other} onChange={(e) => update('honors_other', e.target.value)} />
              </FormField>
            )}
            <label className="checkbox-field">
              <input type="checkbox" checked={form.still_studying} onChange={(e) => update('still_studying', e.target.checked)} />
              I am still studying (expected graduation below)
            </label>
            {form.still_studying && (
              <FormRow>
                <FormField label="Expected graduation">
                  <input className="form-control" value={form.expected_graduation} onChange={(e) => update('expected_graduation', e.target.value)} placeholder="e.g. Dec 2026" />
                </FormField>
                <FormField label="Current year of study">
                  <SelectInput value={form.current_year} onChange={(v) => update('current_year', v)} options={STUDY_YEARS} placeholder="Select" />
                </FormField>
              </FormRow>
            )}
            <FormRow>
              <FormField label="English test">
                <SelectInput value={form.english_test} onChange={(v) => update('english_test', v)} options={ENGLISH_TESTS} />
              </FormField>
              <FormField label="Overall score">
                <input className="form-control" value={form.english_score} onChange={(e) => update('english_score', e.target.value)} placeholder="e.g. 8.0" />
              </FormField>
              <FormField label="Test date">
                <input className="form-control" type="date" value={form.english_test_date} onChange={(e) => update('english_test_date', e.target.value)} />
              </FormField>
            </FormRow>
          </FormSection>
        )}

        {step === 3 && (
          <FormSection title="Goals & constraints" description="These drive filtering, be explicit about funding and regions.">
            <FormField label="Primary target" required>
              <ChipGroup
                options={['MSc', 'PhD', 'Fellowship', 'Internship', 'Mixed']}
                selected={form.target_degree}
                onToggle={(v) => update('target_degree', v as IntakeFormData['target_degree'])}
                multi={false}
              />
            </FormField>
            <FormField label="Program style" hint="Select all styles you would consider">
              <ChipGroup
                options={PROGRAM_STYLE_OPTIONS}
                selected={form.program_styles}
                onToggle={toggleProgramStyle}
              />
            </FormField>
            <FormField label="Target start term" required>
              <SelectInput value={form.target_intake_term} onChange={(v) => update('target_intake_term', v)} options={INTAKE_TERMS} placeholder="Select intake term" />
            </FormField>
            {form.target_intake_term === 'custom' && (
              <FormField label="Custom intake term">
                <input className="form-control" value={form.custom_intake_term} onChange={(e) => update('custom_intake_term', e.target.value)} placeholder="e.g. Winter 2028" />
              </FormField>
            )}
            <FormField label="Funding requirement" required hint="Select every funding level you would accept">
              <ChipGroup
                options={FUNDING_REQUIREMENT_OPTIONS}
                selected={form.funding_requirements}
                onToggle={toggleFundingRequirement}
              />
            </FormField>
            <FormField label="Target regions" required hint="Pick at least one">
              <ChipGroup
                options={REGION_OPTIONS}
                selected={parseChipInput(regionsInput)}
                onToggle={(r) => {
                  const current = parseChipInput(regionsInput);
                  setRegionsInput(chipsToInput(current.includes(r) ? current.filter((x) => x !== r) : [...current, r]));
                }}
              />
              <input className="form-control" style={{ marginTop: '0.5rem' }} value={regionsInput} onChange={(e) => setRegionsInput(e.target.value)} placeholder="Or type: Germany, Europe, UK…" />
            </FormField>
            <FormField label="Countries to prioritize" hint="Order matters, first picks rank higher">
              <ChipGroup
                options={PRIORITY_COUNTRY_CHIPS}
                selected={parseChipInput(countriesInput)}
                onToggle={(c) => {
                  const current = parseChipInput(countriesInput);
                  setCountriesInput(
                    chipsToInput(
                      current.includes(c) ? current.filter((x) => x !== c) : [...current, c],
                    ),
                  );
                }}
              />
              <input
                className="form-control"
                style={{ marginTop: '0.5rem' }}
                value={countriesInput}
                onChange={(e) => setCountriesInput(e.target.value)}
                placeholder="Or type: Germany, United States, Canada…"
              />
            </FormField>
            <label className="checkbox-field">
              <input type="checkbox" checked={form.developing_country_scholarships} onChange={(e) => update('developing_country_scholarships', e.target.checked)} />
              Boost scholarships open to developing-country applicants
            </label>
            <FormField label="Research areas" required hint="Pick at least three">
              <ChipGroup
                options={FIELD_SUGGESTIONS}
                selected={parseChipInput(fieldsInput)}
                onToggle={(f) => {
                  const current = parseChipInput(fieldsInput);
                  setFieldsInput(chipsToInput(current.includes(f) ? current.filter((x) => x !== f) : [...current, f]));
                }}
              />
              <input className="form-control" style={{ marginTop: '0.5rem' }} value={fieldsInput} onChange={(e) => setFieldsInput(e.target.value)} />
            </FormField>
            <FormField label="Research direction (one sentence)">
              <textarea className="form-control" value={form.research_one_liner} onChange={(e) => update('research_one_liner', e.target.value)} rows={2} placeholder="What problems excite you?" />
            </FormField>
            <FormField label="Flagship projects">
              <input className="form-control" value={form.flagship_projects} onChange={(e) => update('flagship_projects', e.target.value)} placeholder="TellO, PAT system, …" />
            </FormField>
            {form.target_degree === 'PhD' && (
              <>
                <FormField label="Preferred supervisors / labs">
                  <input className="form-control" value={form.preferred_supervisors} onChange={(e) => update('preferred_supervisors', e.target.value)} />
                </FormField>
                <label className="checkbox-field">
                  <input type="checkbox" checked={form.open_to_ra} onChange={(e) => update('open_to_ra', e.target.checked)} />
                  Open to research assistant roles before PhD
                </label>
              </>
            )}
            {form.target_degree === 'Fellowship' && (
              <FormField label="Fellowship types">
                <ChipGroup
                  options={FELLOWSHIP_TYPES}
                  selected={form.fellowship_types}
                  onToggle={(v) => {
                    const cur = form.fellowship_types;
                    update('fellowship_types', cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]);
                  }}
                />
              </FormField>
            )}
            <FormField label="Anti-goals" hint="Hard-drop these opportunity patterns">
              <ChipGroup
                options={ANTI_GOAL_OPTIONS.map(({ key, label }) => ({ value: key, label }))}
                selected={form.anti_goals}
                onToggle={(v) => toggleAntiGoal(v as AntiGoalKey)}
              />
            </FormField>
            <FormField label="Other anti-goal">
              <input className="form-control" value={form.anti_goals_other} onChange={(e) => update('anti_goals_other', e.target.value)} />
            </FormField>
          </FormSection>
        )}

        {step === 4 && (
          <>
            <FormSection
              title="Discovery & sources"
              description="Where and how you'd like us to look for opportunities."
            >
              <FormField label="Discovery mode">
                <ChipGroup
                  options={DISCOVERY_MODE_OPTIONS}
                  selected={form.discovery_mode}
                  onToggle={(v) => update('discovery_mode', v as IntakeFormData['discovery_mode'])}
                  multi={false}
                />
              </FormField>
              <FormField label="Sources you already use" hint="Optional, helps prioritize familiar channels">
                <ChipGroup
                  options={SEARCH_SOURCE_OPTIONS}
                  selected={form.search_sources}
                  onToggle={(v) => toggleChipList('search_sources', v)}
                />
              </FormField>
            </FormSection>

            <FormSection
              title="Institution targets"
              description="Specific schools matter for supervisor matching and cold-outreach prep."
            >
              <FormField
                label="Target universities"
                required={form.discovery_mode === 'target_list'}
                hint={
                  form.discovery_mode === 'target_list'
                    ? 'Required when focusing on a target list'
                    : 'Optional, leave blank for open discovery'
                }
              >
                <input
                  className="form-control"
                  value={form.target_universities}
                  onChange={(e) => update('target_universities', e.target.value)}
                  placeholder="TU Dresden, ETH Zurich, MIT, …"
                />
              </FormField>
            </FormSection>

            <FormSection
              title="Network"
              description="People and communities that can unlock referrals or inside-track opportunities."
            >
              <FormField label="Connections worth remembering">
                <input
                  className="form-control"
                  value={form.connections}
                  onChange={(e) => update('connections', e.target.value)}
                  placeholder="Prof. Calandra, DAAD alum network, former lab mates…"
                />
              </FormField>
            </FormSection>

            <FormSection
              title="Mobility & languages"
              description="Relocation openness and language skills feed eligibility and regional scholarship matching."
            >
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={form.open_to_relocation}
                  onChange={(e) => update('open_to_relocation', e.target.checked)}
                />
                Open to relocating for the right funded opportunity
              </label>
              <FormField label="Other languages (besides English)" hint="Used for country-specific programs and DAAD-style filters">
                <ChipGroup
                  options={OTHER_LANGUAGE_OPTIONS}
                  selected={form.other_languages}
                  onToggle={(v) => toggleChipList('other_languages', v)}
                />
              </FormField>
              <FormField label="Mobility constraints or preferences">
                <textarea
                  className="form-control"
                  value={form.mobility_notes}
                  onChange={(e) => update('mobility_notes', e.target.value)}
                  rows={2}
                  placeholder="Partner location, visa history, max time away from home country…"
                />
              </FormField>
            </FormSection>

            <FormSection
              title="Time & notes"
              description="Helps prioritize application workload and capture anything the structured fields miss."
            >
              <FormField label="Hours per week for applications & prep">
                <input
                  className="form-control"
                  type="number"
                  min={1}
                  max={40}
                  value={form.hours_per_week}
                  onChange={(e) => update('hours_per_week', e.target.value)}
                  placeholder="8"
                />
              </FormField>
              <FormField label="Additional notes">
                <textarea
                  className="form-control"
                  value={form.additional_notes}
                  onChange={(e) => update('additional_notes', e.target.value)}
                  rows={3}
                  placeholder="Visa constraints, dependents, disability accommodations, industry pivot goals…"
                />
              </FormField>
            </FormSection>
          </>
        )}

        {step === 5 && (
          <FormSection title="Review & submit" description="Confirm everything looks correct.">
            <div className="review-layout">
              <ReviewBlock
                title="Identity"
                items={[
                  { label: 'Name', value: form.full_name },
                  { label: 'Nationality', value: countryNameByCode(form.nationality_code) },
                  { label: 'Country', value: countryNameByCode(form.current_country_code) || 'n/a' },
                  { label: 'LinkedIn', value: form.linkedin_url },
                ]}
              />
              <ReviewBlock
                title="Goals"
                items={[
                  { label: 'Target', value: `${form.target_degree} · ${resolvedIntakeTerm()}` },
                  { label: 'Program style', value: programStyleReview() },
                  { label: 'Funding', value: fundingReview() },
                  { label: 'Regions', value: regionsInput || 'n/a' },
                  { label: 'Countries', value: countriesInput || 'n/a' },
                  { label: 'Fields', value: fieldsInput || 'n/a' },
                ]}
              />
              <ReviewBlock
                title="Preferences"
                items={[
                  {
                    label: 'Discovery',
                    value:
                      DISCOVERY_MODE_OPTIONS.find((o) => o.value === form.discovery_mode)?.label ??
                      form.discovery_mode,
                  },
                  { label: 'Universities', value: form.target_universities || 'n/a' },
                  { label: 'Sources', value: form.search_sources.join(', ') || 'n/a' },
                  { label: 'Relocation', value: form.open_to_relocation ? 'Open' : 'Prefer current region' },
                  { label: 'Languages', value: form.other_languages.join(', ') || 'n/a' },
                  { label: 'Hours/week', value: form.hours_per_week || 'n/a' },
                ]}
              />
            </div>
            <ReviewBlock
              title="Education & CV"
              items={[
                { label: 'Degree', value: `${form.degree_level} · ${resolvedField()}` },
                { label: 'Institution', value: form.institution },
                { label: 'CV', value: `${cvText.length.toLocaleString()} chars${cvFilename ? ` (${cvFilename})` : ''}` },
              ]}
            />
          </FormSection>
        )}

        <div className="form-nav">
          {step > 0 && (
            <Button variant="secondary" onClick={goBack} disabled={saveDraftMutation.isPending || cvUploading}>
              Back
            </Button>
          )}
          <Button
            variant={step === FORM_STEPS.length - 1 ? 'gold' : 'primary'}
            onClick={goNext}
            disabled={!canNext() || saveDraftMutation.isPending || submitMutation.isPending || cvUploading}
          >
            {step === FORM_STEPS.length - 1
              ? submitMutation.isPending
                ? 'Submitting…'
                : 'Submit profile'
              : 'Continue'}
          </Button>
        </div>
      </div>
    </>
  );
}
