import { COUNTRIES, countryNameByCode } from '../../data/countries';
import {
  DEGREE_LEVELS,
  ENGLISH_TESTS,
  FELLOWSHIP_TYPES,
  GPA_SCALES,
  HONORS_OPTIONS,
  INTAKE_TERMS,
  MONTHS,
  SEARCH_SOURCE_OPTIONS,
  STUDY_FIELDS,
  STUDY_YEARS,
  graduationYears,
} from '../../data/form-options';
import {
  ChipGroup,
  CountryCombobox,
  FileDropZone,
  FormField,
  FormRow,
  FormSection,
  ReviewBlock,
  SelectInput,
  useFieldId,
} from '../../components/form/FormControls';
import { IntakeFormData } from '../../types/intake';

function toggle(list: string[], v: string) {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export function StepIdentity({
  form,
  onUpdate,
}: {
  form: IntakeFormData;
  onUpdate: <K extends keyof IntakeFormData>(k: K, v: IntakeFormData[K]) => void;
}) {
  const nameId = useFieldId('name');
  const emailId = useFieldId('email');
  const natId = useFieldId('nat');
  const resId = useFieldId('res');
  const liId = useFieldId('li');

  return (
    <>
      <FormSection title="Personal details" description="Used for eligibility and your official profile record.">
        <FormRow>
          <FormField label="Full legal name" required htmlFor={nameId}>
            <input id={nameId} className="form-control" value={form.full_name} onChange={(e) => onUpdate('full_name', e.target.value)} autoComplete="name" />
          </FormField>
          <FormField label="Email" hint="Optional — for deadline reminders" htmlFor={emailId}>
            <input id={emailId} className="form-control" type="email" value={form.email} onChange={(e) => onUpdate('email', e.target.value)} autoComplete="email" />
          </FormField>
        </FormRow>
        <FormRow>
          <FormField label="Nationality" required htmlFor={natId}>
            <CountryCombobox id={natId} value={form.nationality_code} onChange={(v) => onUpdate('nationality_code', v)} countries={COUNTRIES} />
          </FormField>
          <FormField label="Country of residence" htmlFor={resId}>
            <CountryCombobox id={resId} value={form.current_country_code} onChange={(v) => onUpdate('current_country_code', v)} countries={COUNTRIES} placeholder="Where you live now" />
          </FormField>
        </FormRow>
      </FormSection>
      <FormSection title="Professional links">
        <FormField label="LinkedIn" required htmlFor={liId}>
          <input id={liId} className="form-control" type="url" value={form.linkedin_url} onChange={(e) => onUpdate('linkedin_url', e.target.value)} placeholder="https://linkedin.com/in/..." />
        </FormField>
        <FormRow>
          <FormField label="GitHub">
            <input className="form-control" type="url" value={form.github_url} onChange={(e) => onUpdate('github_url', e.target.value)} />
          </FormField>
          <FormField label="Portfolio">
            <input className="form-control" type="url" value={form.website_url} onChange={(e) => onUpdate('website_url', e.target.value)} />
          </FormField>
        </FormRow>
        <FormRow>
          <FormField label="Google Scholar">
            <input className="form-control" type="url" value={form.google_scholar_url} onChange={(e) => onUpdate('google_scholar_url', e.target.value)} />
          </FormField>
          <FormField label="ORCID">
            <input className="form-control" value={form.orcid} onChange={(e) => onUpdate('orcid', e.target.value)} placeholder="0000-0000-0000-0000" />
          </FormField>
        </FormRow>
      </FormSection>
    </>
  );
}

export function StepCv({
  cvText,
  onCvChange,
  onFile,
}: {
  cvText: string;
  onCvChange: (v: string) => void;
  onFile: (f: File) => void;
}) {
  const cvId = useFieldId('cv');
  return (
    <>
      <p className="step-lead">Upload your CV or paste plain text. PDF and .txt supported.</p>
      <FileDropZone accept=".txt,.pdf,text/plain,application/pdf" label="Drop CV file here" hint="PDF or plain text" onFile={onFile} />
      <FormField label="CV text" required hint={`${cvText.length} characters — minimum 100`} htmlFor={cvId}>
        <textarea id={cvId} className="form-control cv-textarea" rows={14} value={cvText} onChange={(e) => onCvChange(e.target.value)} placeholder="Paste or upload your CV…" />
      </FormField>
    </>
  );
}

export function StepEducation({
  form,
  onUpdate,
}: {
  form: IntakeFormData;
  onUpdate: <K extends keyof IntakeFormData>(k: K, v: IntakeFormData[K]) => void;
}) {
  return (
    <>
      <FormSection title="Qualification">
        <FormRow>
          <FormField label="Degree level" required>
            <SelectInput value={form.degree_level} onChange={(v) => onUpdate('degree_level', v)} options={DEGREE_LEVELS} placeholder="Select degree" />
          </FormField>
          <FormField label="Field of study" required>
            <SelectInput value={form.field_of_study} onChange={(v) => onUpdate('field_of_study', v)} options={STUDY_FIELDS} placeholder="Select field" />
          </FormField>
        </FormRow>
        {form.field_of_study === 'Other' && (
          <FormField label="Specify field">
            <input className="form-control" value={form.field_of_study_other} onChange={(e) => onUpdate('field_of_study_other', e.target.value)} />
          </FormField>
        )}
        <FormField label="Institution" required>
          <input className="form-control" value={form.institution} onChange={(e) => onUpdate('institution', e.target.value)} />
        </FormField>
        <label className="checkbox-field">
          <input type="checkbox" checked={form.still_studying} onChange={(e) => onUpdate('still_studying', e.target.checked)} />
          Still completing this degree
        </label>
        {form.still_studying ? (
          <FormRow>
            <FormField label="Expected graduation">
              <SelectInput value={form.expected_graduation} onChange={(v) => onUpdate('expected_graduation', v)} options={INTAKE_TERMS.filter((t) => t !== 'custom')} placeholder="Select term" />
            </FormField>
            <FormField label="Current year">
              <SelectInput value={form.current_year} onChange={(v) => onUpdate('current_year', v)} options={STUDY_YEARS} placeholder="Select" />
            </FormField>
          </FormRow>
        ) : (
          <FormRow>
            <FormField label="Graduation month">
              <SelectInput value={form.graduation_month} onChange={(v) => onUpdate('graduation_month', v)} options={MONTHS} placeholder="Month" />
            </FormField>
            <FormField label="Year">
              <SelectInput value={form.graduation_year} onChange={(v) => onUpdate('graduation_year', v)} options={graduationYears().map(String)} placeholder="Year" />
            </FormField>
          </FormRow>
        )}
        <FormRow>
          <FormField label="GPA / grade">
            <input className="form-control" value={form.gpa} onChange={(e) => onUpdate('gpa', e.target.value)} />
          </FormField>
          <FormField label="Scale">
            <SelectInput value={form.gpa_scale} onChange={(v) => onUpdate('gpa_scale', v)} options={GPA_SCALES} />
          </FormField>
        </FormRow>
        <FormField label="Honours">
          <SelectInput value={form.honors} onChange={(v) => onUpdate('honors', v)} options={HONORS_OPTIONS} placeholder="If applicable" />
        </FormField>
      </FormSection>
      <FormSection title="English proficiency">
        <FormRow>
          <FormField label="Test">
            <SelectInput value={form.english_test} onChange={(v) => onUpdate('english_test', v)} options={ENGLISH_TESTS} />
          </FormField>
          {form.english_test !== 'None' && form.english_test !== 'Exempt' && (
            <>
              <FormField label="Score">
                <input className="form-control" value={form.english_score} onChange={(e) => onUpdate('english_score', e.target.value)} />
              </FormField>
              <FormField label="Test date">
                <input className="form-control" type="date" value={form.english_test_date} onChange={(e) => onUpdate('english_test_date', e.target.value)} />
              </FormField>
            </>
          )}
        </FormRow>
      </FormSection>
    </>
  );
}

const REGIONS = ['Germany', 'Europe', 'UK', 'USA', 'Canada', 'Australia', 'Asia', 'Global'];
const FIELDS = ['robotics', 'computer vision', 'human-robot interaction', 'machine learning', 'computational modelling', 'reinforcement learning', 'NLP', 'edge AI', 'social robotics'];
const ANTI = [
  { value: 'unpaid_internships', label: 'Unpaid / volunteer' },
  { value: 'non_stem', label: 'Non-STEM' },
  { value: 'no_funding_info', label: 'No funding clarity' },
  { value: 'online_only', label: 'Online-only' },
  { value: 'undergrad_only', label: 'Undergraduate-only' },
  { value: 'bootcamp', label: 'Bootcamp scholarships' },
] as const;

export function StepGoals({
  form,
  flagshipInput,
  onUpdate,
  onFlagshipChange,
}: {
  form: IntakeFormData;
  flagshipInput: string;
  onUpdate: <K extends keyof IntakeFormData>(k: K, v: IntakeFormData[K]) => void;
  onFlagshipChange: (v: string) => void;
}) {
  const priorityCountries = COUNTRIES.filter((c) => c.code !== 'OTHER');

  return (
    <>
      <FormSection title="Target program">
        <FormField label="Primary target" required>
          <ChipGroup options={['MSc', 'PhD', 'Fellowship', 'Internship', 'Mixed']} selected={form.target_degree} onToggle={(v) => onUpdate('target_degree', v as IntakeFormData['target_degree'])} multi={false} />
        </FormField>
        <FormField label="Program style">
          <ChipGroup
            options={[
              { value: 'research_aligned', label: 'Research-aligned' },
              { value: 'coursework', label: 'Coursework' },
              { value: 'no_preference', label: 'No preference' },
            ]}
            selected={form.program_style}
            onToggle={(v) => onUpdate('program_style', v as IntakeFormData['program_style'])}
            multi={false}
          />
        </FormField>
        <FormRow>
          <FormField label="Target intake" required>
            <SelectInput value={form.target_intake_term} onChange={(v) => onUpdate('target_intake_term', v)} options={INTAKE_TERMS} />
          </FormField>
          {form.target_intake_term === 'custom' && (
            <FormField label="Specify term">
              <input className="form-control" value={form.custom_intake_term} onChange={(e) => onUpdate('custom_intake_term', e.target.value)} />
            </FormField>
          )}
        </FormRow>
        <FormField label="Funding requirement" required>
          <ChipGroup
            options={[
              { value: 'full_only', label: 'Fully funded only' },
              { value: 'partial_ok', label: 'Partial OK' },
              { value: 'self_fund_possible', label: 'Self-fund possible' },
            ]}
            selected={form.funding_requirement}
            onToggle={(v) => onUpdate('funding_requirement', v as IntakeFormData['funding_requirement'])}
            multi={false}
          />
        </FormField>
      </FormSection>
      <FormSection title="Geography">
        <FormField label="Target regions" required hint={`${form.target_regions.length} selected — need at least 1`}>
          <ChipGroup options={REGIONS} selected={form.target_regions} onToggle={(v) => onUpdate('target_regions', toggle(form.target_regions, v))} />
        </FormField>
        <FormField label="Countries to prioritize" hint="Search and select">
          <CountryCombobox
            value=""
            onChange={(code) => {
              const name = countryNameByCode(code);
              if (name && !form.target_countries_priority.includes(name)) {
                onUpdate('target_countries_priority', [...form.target_countries_priority, name]);
              }
            }}
            countries={priorityCountries}
            placeholder="Add priority country…"
          />
          {form.target_countries_priority.length > 0 && (
            <ChipGroup options={form.target_countries_priority} selected={form.target_countries_priority} onToggle={(v) => onUpdate('target_countries_priority', form.target_countries_priority.filter((c) => c !== v))} />
          )}
        </FormField>
      </FormSection>
      <FormSection title="Research focus">
        <FormField label="Research areas" required hint={`${form.target_fields.length}/3 minimum`}>
          <ChipGroup options={FIELDS} selected={form.target_fields} onToggle={(v) => onUpdate('target_fields', toggle(form.target_fields, v))} />
        </FormField>
        <FormField label="What problems excite you?">
          <textarea className="form-control" rows={3} value={form.research_one_liner} onChange={(e) => onUpdate('research_one_liner', e.target.value)} />
        </FormField>
        <FormField label="Flagship projects">
          <input className="form-control" value={flagshipInput} onChange={(e) => onFlagshipChange(e.target.value)} placeholder="TellO, thesis project…" />
        </FormField>
        {form.target_degree === 'Fellowship' && (
          <FormField label="Fellowship types">
            <ChipGroup options={FELLOWSHIP_TYPES} selected={form.fellowship_types} onToggle={(v) => onUpdate('fellowship_types', toggle(form.fellowship_types, v))} />
          </FormField>
        )}
      </FormSection>
      <FormSection title="Exclude">
        <ChipGroup options={ANTI} selected={form.anti_goals} onToggle={(v) => onUpdate('anti_goals', toggle(form.anti_goals, v) as IntakeFormData['anti_goals'])} />
      </FormSection>
    </>
  );
}

export function StepPreferences({
  form,
  onUpdate,
}: {
  form: IntakeFormData;
  onUpdate: <K extends keyof IntakeFormData>(k: K, v: IntakeFormData[K]) => void;
}) {
  return (
    <>
      <FormSection title="Discovery">
        <FormField label="Target universities" hint="Leave blank to explore broadly">
          <input className="form-control" value={form.target_universities.join(', ')} onChange={(e) => onUpdate('target_universities', e.target.value.split(/[,;]/).map((s) => s.trim()).filter(Boolean))} />
        </FormField>
        <FormField label="Key connections">
          <input className="form-control" value={form.connections} onChange={(e) => onUpdate('connections', e.target.value)} />
        </FormField>
      </FormSection>
      <FormSection title="Your workflow">
        <FormField label="Hours per week for applications">
          <input className="form-control form-control-narrow" type="number" min={1} max={40} value={form.hours_per_week} onChange={(e) => onUpdate('hours_per_week', e.target.value ? Number(e.target.value) : '')} />
        </FormField>
        <FormField label="Where you search today">
          <ChipGroup options={SEARCH_SOURCE_OPTIONS} selected={form.search_sources} onToggle={(v) => onUpdate('search_sources', toggle(form.search_sources, v))} />
        </FormField>
        <FormField label="Additional notes">
          <textarea className="form-control" rows={3} value={form.additional_notes} onChange={(e) => onUpdate('additional_notes', e.target.value)} />
        </FormField>
      </FormSection>
    </>
  );
}


export function StepReview({
  form,
  cvText,
}: {
  form: IntakeFormData;
  cvText: string;
}) {
  const term = form.target_intake_term === 'custom' ? form.custom_intake_term : form.target_intake_term;
  const field = form.field_of_study === 'Other' ? form.field_of_study_other : form.field_of_study;
  return (
    <div className="review-layout">
      <ReviewBlock title="Identity" items={[
        { label: 'Name', value: form.full_name },
        { label: 'Nationality', value: countryNameByCode(form.nationality_code) },
        { label: 'LinkedIn', value: form.linkedin_url },
      ]} />
      <ReviewBlock title="Education" items={[
        { label: 'Degree', value: `${form.degree_level} — ${field}` },
        { label: 'Institution', value: form.institution },
        { label: 'English', value: form.english_test },
      ]} />
      <ReviewBlock title="Goals" items={[
        { label: 'Target', value: `${form.target_degree} · ${term}` },
        { label: 'Funding', value: form.funding_requirement.replace(/_/g, ' ') },
        { label: 'Regions', value: form.target_regions.join(', ') },
        { label: 'Fields', value: form.target_fields.join(', ') },
      ]} />
      <ReviewBlock title="CV" items={[
        { label: 'Length', value: `${cvText.length} characters` },
        { label: 'Projects', value: form.flagship_projects.join(', ') },
      ]} />
    </div>
  );
}
