import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { intakeApi } from '../api/intake';
import {
  ANTI_GOAL_OPTIONS,
  DEFAULT_INTAKE_FORM,
  FIELD_SUGGESTIONS,
  IntakeFormData,
  REGION_OPTIONS,
  WIZARD_STEPS,
  chipsToInput,
  mergeForm,
  normalizeDraftForm,
  parseChipInput,
} from '../types/intake';

function setField<K extends keyof IntakeFormData>(
  form: IntakeFormData,
  key: K,
  value: IntakeFormData[K],
): IntakeFormData {
  return { ...form, [key]: value };
}

function ChipToggle({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`chip-toggle${selected ? ' selected' : ''}`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function PromptPanel({
  prompt,
  instructions,
  savePath,
}: {
  prompt: string;
  instructions: string;
  savePath: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="prompt-panel">
      <p className="prompt-instructions">{instructions}</p>
      <p className="prompt-save-hint">
        Save LLM output to: <code>{savePath}</code>
      </p>
      <textarea className="prompt-textarea" readOnly value={prompt} rows={18} />
      <div className="actions-row">
        <button type="button" className="btn" onClick={copy}>
          {copied ? 'Copied!' : 'Copy prompt'}
        </button>
      </div>
    </div>
  );
}

export default function ProfileIntake() {
  const queryClient = useQueryClient();
  const { data: draft, isLoading } = useQuery({
    queryKey: ['intake-draft'],
    queryFn: intakeApi.getDraft,
  });

  const [step, setStep] = useState(0);
  const [form, setForm] = useState<IntakeFormData>(DEFAULT_INTAKE_FORM);
  const [cvText, setCvText] = useState('');
  const [fieldsInput, setFieldsInput] = useState('');
  const [regionsInput, setRegionsInput] = useState('');
  const [extractionJson, setExtractionJson] = useState('');
  const [pass1Prompt, setPass1Prompt] = useState<{ prompt: string; instructions: string; save_path: string } | null>(null);
  const [pass2Prompt, setPass2Prompt] = useState<{ prompt: string; instructions: string; save_path: string } | null>(null);
  const [validateResult, setValidateResult] = useState<{
    valid: boolean;
    errors: string[];
    fields_needing_review?: string[];
    confidence?: string;
    profile?: Record<string, unknown>;
  } | null>(null);

  useEffect(() => {
    if (draft) {
      setStep(draft.step ?? 0);
      const normalized = normalizeDraftForm(draft.form as Partial<IntakeFormData> & Record<string, unknown>);
      setForm(normalized);
      setCvText(draft.cv_text ?? '');
      setFieldsInput(chipsToInput(normalized.target_fields));
      setRegionsInput(chipsToInput(normalized.target_regions));
    }
  }, [draft]);

  const saveDraftMutation = useMutation({
    mutationFn: ({ s, f, cv }: { s: number; f: IntakeFormData; cv: string }) =>
      intakeApi.saveDraft(s, f, cv),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['intake-draft'] }),
  });

  const persist = useCallback(
    async (nextStep: number, nextForm: IntakeFormData, nextCv: string) => {
      const withChips = setField(
        setField(nextForm, 'target_fields', parseChipInput(fieldsInput)),
        'target_regions',
        parseChipInput(regionsInput),
      );
      await saveDraftMutation.mutateAsync({ s: nextStep, f: withChips, cv: nextCv });
      setForm(withChips);
      setStep(nextStep);
    },
    [fieldsInput, regionsInput, saveDraftMutation],
  );

  const extractionMutation = useMutation({
    mutationFn: () => {
      const withChips = setField(
        setField(form, 'target_fields', parseChipInput(fieldsInput)),
        'target_regions',
        parseChipInput(regionsInput),
      );
      return intakeApi.generateExtractionPrompt(6, withChips, cvText);
    },
    onSuccess: (data) => {
      setPass1Prompt(data);
      setStep(6);
    },
  });

  const validateMutation = useMutation({
    mutationFn: async () => {
      const parsed = JSON.parse(extractionJson) as Record<string, unknown>;
      return intakeApi.validateExtraction(parsed);
    },
    onSuccess: (data) => setValidateResult(data),
    onError: (err: Error) =>
      setValidateResult({ valid: false, errors: [err.message] }),
  });

  const confirmMutation = useMutation({
    mutationFn: async () => {
      const parsed = JSON.parse(extractionJson) as Record<string, unknown>;
      return intakeApi.confirmStructured(parsed);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['intake-draft'] }),
  });

  const compileMutation = useMutation({
    mutationFn: async () => {
      let data: Record<string, unknown> | undefined;
      if (validateResult?.profile) {
        data = validateResult.profile;
      } else if (extractionJson.trim()) {
        data = JSON.parse(extractionJson) as Record<string, unknown>;
      }
      return intakeApi.generateCompilePrompt(data);
    },
    onSuccess: (data) => {
      setPass2Prompt(data);
      setStep(8);
    },
  });

  const update = <K extends keyof IntakeFormData>(key: K, value: IntakeFormData[K]) => {
    setForm((prev) => setField(prev, key, value));
  };

  const toggleRegion = (region: string) => {
    const current = parseChipInput(regionsInput);
    const next = current.includes(region)
      ? current.filter((r) => r !== region)
      : [...current, region];
    setRegionsInput(chipsToInput(next));
  };

  const toggleField = (field: string) => {
    const current = parseChipInput(fieldsInput);
    const next = current.includes(field)
      ? current.filter((f) => f !== field)
      : [...current, field];
    setFieldsInput(chipsToInput(next));
  };

  const toggleAntiGoal = (key: (typeof ANTI_GOAL_OPTIONS)[number]['key']) => {
    const current = form.anti_goals;
    update(
      'anti_goals',
      current.includes(key) ? current.filter((k) => k !== key) : [...current, key],
    );
  };

  const canNext = (): boolean => {
    switch (step) {
      case 0:
        return !!(form.full_name && form.nationality && form.linkedin_url);
      case 1:
        return cvText.trim().length > 100;
      case 2:
        return !!(form.degree_level && form.field_of_study && form.institution);
      case 3:
        return !!(
          form.target_intake_term &&
          parseChipInput(regionsInput).length >= 1 &&
          parseChipInput(fieldsInput).length >= 3
        );
      default:
        return true;
    }
  };

  const goNext = async () => {
    if (!canNext()) return;
    if (step === 5) {
      await persist(5, form, cvText);
      extractionMutation.mutate();
      return;
    }
    await persist(step + 1, form, cvText);
  };

  const goBack = async () => {
    if (step > 0) await persist(step - 1, form, cvText);
  };

  const handleCvFile = async (file: File) => {
    const text = await file.text();
    setCvText(text);
    await intakeApi.saveCv(text);
  };

  if (isLoading) return <div className="empty-state">Loading intake draft...</div>;

  const progress = ((step + 1) / WIZARD_STEPS.length) * 100;

  return (
    <>
      <div className="page-header intake-header">
        <div>
          <h2>Profile Intake</h2>
          <p className="intake-subtitle">
            Build your profile and generate LLM prompts — no API keys required yet.
          </p>
        </div>
        <Link to="/profile" className="btn btn-secondary">
          Quick profile
        </Link>
      </div>

      <div className="intake-progress">
        <div className="intake-step-labels">
          {WIZARD_STEPS.map((s) => (
            <span
              key={s.id}
              className={`intake-step-dot${s.id === step ? ' active' : ''}${s.id < step ? ' done' : ''}`}
              title={s.label}
            >
              {s.label}
            </span>
          ))}
        </div>
        <div className="progress-bar">
          <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="detail-panel intake-panel">
        {step === 0 && (
          <>
            <h3>Step 1 — Identity</h3>
            <p className="step-hint">~1 min. Used for eligibility and profile truth.</p>
            <label>Full name *</label>
            <input value={form.full_name} onChange={(e) => update('full_name', e.target.value)} />
            <label>Nationality (country of citizenship) *</label>
            <input value={form.nationality} onChange={(e) => update('nationality', e.target.value)} placeholder="e.g. Nepal" />
            <label>Country you live in now</label>
            <input value={form.current_country} onChange={(e) => update('current_country', e.target.value)} />
            <label>LinkedIn URL *</label>
            <input value={form.linkedin_url} onChange={(e) => update('linkedin_url', e.target.value)} />
            <label>GitHub URL</label>
            <input value={form.github_url} onChange={(e) => update('github_url', e.target.value)} />
            <label>Portfolio / website</label>
            <input value={form.website_url} onChange={(e) => update('website_url', e.target.value)} />
          </>
        )}

        {step === 1 && (
          <>
            <h3>Step 2 — CV</h3>
            <p className="step-hint">
              Paste CV text or upload a .txt export. The LLM merges this with your form answers.
            </p>
            <label>Upload CV (.txt)</label>
            <input
              type="file"
              accept=".txt,text/plain"
              onChange={(e) => e.target.files?.[0] && handleCvFile(e.target.files[0])}
            />
            <label>CV plain text *</label>
            <textarea
              className="cv-textarea"
              value={cvText}
              onChange={(e) => setCvText(e.target.value)}
              placeholder="Paste full CV text here..."
              rows={14}
            />
            <p className="char-count">{cvText.length} characters {cvText.length < 100 ? '(need more)' : ''}</p>
          </>
        )}

        {step === 2 && (
          <>
            <h3>Step 3 — Education & language</h3>
            <p className="step-hint">Pre-fill what you know; the LLM completes details from your CV.</p>
            <label>Highest degree *</label>
            <input value={form.degree_level} onChange={(e) => update('degree_level', e.target.value)} placeholder="e.g. BSc" />
            <label>Field of study *</label>
            <input value={form.field_of_study} onChange={(e) => update('field_of_study', e.target.value)} />
            <label>Institution *</label>
            <input value={form.institution} onChange={(e) => update('institution', e.target.value)} />
            <label>Graduation month & year</label>
            <input value={form.graduation_date} onChange={(e) => update('graduation_date', e.target.value)} placeholder="e.g. Dec 2025" />
            <label>GPA / grade + scale</label>
            <input value={form.gpa} onChange={(e) => update('gpa', e.target.value)} placeholder="e.g. 82.11/100" />
            <label>Honors</label>
            <input value={form.honors} onChange={(e) => update('honors', e.target.value)} />
            <label className="checkbox-row">
              <input type="checkbox" checked={form.still_studying} onChange={(e) => update('still_studying', e.target.checked)} />
              Still studying
            </label>
            {form.still_studying && (
              <>
                <label>Expected graduation</label>
                <input value={form.expected_graduation} onChange={(e) => update('expected_graduation', e.target.value)} />
                <label>Current year of study</label>
                <input value={form.current_year} onChange={(e) => update('current_year', e.target.value)} />
              </>
            )}
            <label>English test</label>
            <select value={form.english_test} onChange={(e) => update('english_test', e.target.value)}>
              <option value="IELTS">IELTS</option>
              <option value="TOEFL">TOEFL</option>
              <option value="Duolingo">Duolingo</option>
              <option value="Exempt">Exempt</option>
              <option value="None">None yet</option>
            </select>
            <label>Score</label>
            <input value={form.english_score} onChange={(e) => update('english_score', e.target.value)} placeholder="e.g. 8.0" />
            <label>Test date</label>
            <input value={form.english_test_date} onChange={(e) => update('english_test_date', e.target.value)} />
          </>
        )}

        {step === 3 && (
          <>
            <h3>Step 4 — Goals & constraints</h3>
            <p className="step-hint">These drive filtering — be explicit about funding and regions.</p>

            <label>Primary target *</label>
            <div className="chip-row">
              {(['MSc', 'PhD', 'Fellowship', 'Internship', 'Mixed'] as const).map((d) => (
                <ChipToggle key={d} label={d} selected={form.target_degree === d} onClick={() => update('target_degree', d)} />
              ))}
            </div>

            <label>Program style</label>
            <div className="chip-row">
              <ChipToggle label="Research-aligned" selected={form.program_style === 'research_aligned'} onClick={() => update('program_style', 'research_aligned')} />
              <ChipToggle label="Coursework" selected={form.program_style === 'coursework'} onClick={() => update('program_style', 'coursework')} />
              <ChipToggle label="No preference" selected={form.program_style === 'no_preference'} onClick={() => update('program_style', 'no_preference')} />
            </div>

            <label>Target start term *</label>
            <input value={form.target_intake_term} onChange={(e) => update('target_intake_term', e.target.value)} placeholder="e.g. Fall 2027" />

            <label>Funding requirement *</label>
            <div className="chip-row">
              <ChipToggle label="Fully funded only" selected={form.funding_requirement === 'full_only'} onClick={() => update('funding_requirement', 'full_only')} />
              <ChipToggle label="Partial OK" selected={form.funding_requirement === 'partial_ok'} onClick={() => update('funding_requirement', 'partial_ok')} />
              <ChipToggle label="Self-fund possible" selected={form.funding_requirement === 'self_fund_possible'} onClick={() => update('funding_requirement', 'self_fund_possible')} />
            </div>

            <label>Target regions * (pick or type below)</label>
            <div className="chip-row">
              {REGION_OPTIONS.map((r) => (
                <ChipToggle key={r} label={r} selected={parseChipInput(regionsInput).includes(r)} onClick={() => toggleRegion(r)} />
              ))}
            </div>
            <input value={regionsInput} onChange={(e) => setRegionsInput(e.target.value)} placeholder="Germany, Europe, UK..." />

            <label>Countries to prioritize</label>
            <input value={form.target_countries_priority} onChange={(e) => update('target_countries_priority', e.target.value)} placeholder="e.g. Germany first" />

            <label className="checkbox-row">
              <input type="checkbox" checked={form.developing_country_scholarships} onChange={(e) => update('developing_country_scholarships', e.target.checked)} />
              Prefer scholarships open to developing-country applicants
            </label>

            <label>Research areas * (pick 3+ or type below)</label>
            <div className="chip-row">
              {FIELD_SUGGESTIONS.map((f) => (
                <ChipToggle key={f} label={f} selected={parseChipInput(fieldsInput).includes(f)} onClick={() => toggleField(f)} />
              ))}
            </div>
            <input value={fieldsInput} onChange={(e) => setFieldsInput(e.target.value)} />

            <label>One sentence — what problems excite you?</label>
            <textarea value={form.research_one_liner} onChange={(e) => update('research_one_liner', e.target.value)} rows={2} />

            <label>Flagship projects to remember</label>
            <input value={form.flagship_projects} onChange={(e) => update('flagship_projects', e.target.value)} placeholder="e.g. TellO, PAT system" />

            {form.target_degree === 'PhD' && (
              <>
                <label>Preferred supervisors / labs</label>
                <input value={form.preferred_supervisors} onChange={(e) => update('preferred_supervisors', e.target.value)} />
                <label className="checkbox-row">
                  <input type="checkbox" checked={form.open_to_ra} onChange={(e) => update('open_to_ra', e.target.checked)} />
                  Open to RA positions before PhD
                </label>
              </>
            )}

            {form.target_degree === 'Fellowship' && (
              <>
                <label>Fellowship types of interest</label>
                <input
                  value={chipsToInput(form.fellowship_types)}
                  onChange={(e) => update('fellowship_types', parseChipInput(e.target.value))}
                  placeholder="Research, Leadership, Country-specific..."
                />
              </>
            )}

            <label>Anti-goals — hard-drop these patterns</label>
            <div className="chip-row wrap">
              {ANTI_GOAL_OPTIONS.map(({ key, label }) => (
                <ChipToggle key={key} label={label} selected={form.anti_goals.includes(key)} onClick={() => toggleAntiGoal(key)} />
              ))}
            </div>
            <label>Other anti-goal</label>
            <input value={form.anti_goals_other} onChange={(e) => update('anti_goals_other', e.target.value)} />
          </>
        )}

        {step === 4 && (
          <>
            <h3>Step 5 — Optional depth</h3>
            <p className="step-hint">Improves ranking and agent context. Skip if unsure.</p>
            <label>Target universities (blank = discovery mode)</label>
            <input value={form.target_universities} onChange={(e) => update('target_universities', e.target.value)} />
            <label>Connections worth remembering</label>
            <input value={form.connections} onChange={(e) => update('connections', e.target.value)} />
            <label>Hours per week for applications + prep</label>
            <input value={form.hours_per_week} onChange={(e) => update('hours_per_week', e.target.value)} placeholder="e.g. 15" />
            <label>Where you search today</label>
            <input value={form.search_sources} onChange={(e) => update('search_sources', e.target.value)} />
            <label>Anything else (1–2 sentences)</label>
            <textarea value={form.additional_notes} onChange={(e) => update('additional_notes', e.target.value)} rows={3} />
          </>
        )}

        {step === 5 && (
          <>
            <h3>Step 6 — Review</h3>
            <div className="review-grid">
              <div><strong>Name</strong><br />{form.full_name}</div>
              <div><strong>Target</strong><br />{form.target_degree} · {form.target_intake_term}</div>
              <div><strong>Funding</strong><br />{form.funding_requirement.replace('_', ' ')}</div>
              <div><strong>Regions</strong><br />{regionsInput || '—'}</div>
              <div><strong>Fields</strong><br />{fieldsInput || '—'}</div>
              <div><strong>CV</strong><br />{cvText.length} chars</div>
            </div>
            <p className="step-hint">Next: generate Pass 1 extraction prompt for your external LLM.</p>
          </>
        )}

        {step === 6 && pass1Prompt && (
          <>
            <h3>Pass 1 — Extraction prompt</h3>
            <p className="step-hint">
              1. Copy prompt → run in ChatGPT/Claude → save JSON to{' '}
              <code>docs/profile/intake/extraction-output.json</code>
            </p>
            <PromptPanel {...pass1Prompt} savePath={pass1Prompt.save_path} />
          </>
        )}

        {step === 7 && (
          <>
            <h3>Validate extraction JSON</h3>
            <p className="step-hint">Paste the LLM JSON output below. We validate against the schema before compile.</p>
            <textarea
              className="cv-textarea"
              value={extractionJson}
              onChange={(e) => setExtractionJson(e.target.value)}
              placeholder='{"schema_version": "1.0", "identity": {...}, ...}'
              rows={12}
            />
            {validateResult && (
              <div className={`validate-result${validateResult.valid ? ' ok' : ' err'}`}>
                {validateResult.valid ? (
                  <>
                    <p>Validation passed — confidence: {validateResult.confidence}</p>
                    {validateResult.fields_needing_review && validateResult.fields_needing_review.length > 0 && (
                      <>
                        <p>Review these fields:</p>
                        <ul>
                          {validateResult.fields_needing_review.map((f) => (
                            <li key={f}>{f}</li>
                          ))}
                        </ul>
                      </>
                    )}
                  </>
                ) : (
                  <pre>{validateResult.errors.join('\n')}</pre>
                )}
              </div>
            )}
            <div className="actions-row">
              <button type="button" className="btn btn-secondary" onClick={() => validateMutation.mutate()} disabled={validateMutation.isPending || !extractionJson.trim()}>
                Validate JSON
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => confirmMutation.mutate()}
                disabled={!validateResult?.valid || confirmMutation.isPending}
              >
                {confirmMutation.isSuccess ? 'Saved structured-profile.json' : 'Confirm & save profile'}
              </button>
            </div>
          </>
        )}

        {step === 8 && pass2Prompt && (
          <>
            <h3>Pass 2 — Compile prompt</h3>
            <p className="step-hint">
              Generates filter rules + profile truth. Save artifacts to <code>docs/profile/compiled/</code>
            </p>
            <PromptPanel {...pass2Prompt} savePath={pass2Prompt.save_path} />
          </>
        )}

        {step <= 5 && (
          <div className="actions-row intake-nav">
            {step > 0 && (
              <button type="button" className="btn btn-secondary" onClick={goBack} disabled={saveDraftMutation.isPending}>
                Back
              </button>
            )}
            <button type="button" className="btn" onClick={goNext} disabled={!canNext() || saveDraftMutation.isPending || extractionMutation.isPending}>
              {step === 5 ? (extractionMutation.isPending ? 'Generating prompt...' : 'Generate Pass 1 prompt') : 'Continue'}
            </button>
          </div>
        )}

        {step === 6 && (
          <div className="actions-row intake-nav">
            <button type="button" className="btn btn-secondary" onClick={() => setStep(5)}>Back to review</button>
            <button type="button" className="btn" onClick={() => setStep(7)}>I have the JSON — validate</button>
          </div>
        )}

        {step === 7 && validateResult?.valid && (
          <div className="actions-row intake-nav">
            <button type="button" className="btn" onClick={() => compileMutation.mutate()} disabled={compileMutation.isPending}>
              {compileMutation.isPending ? 'Generating...' : 'Generate Pass 2 compile prompt'}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
