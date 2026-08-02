/** Profile intake form — mirrors docs/profile/intake/form-v1.md */

export type TargetDegree = 'MSc' | 'PhD' | 'Fellowship' | 'Internship' | 'Mixed';
export type ProgramStyle = 'research_aligned' | 'coursework' | 'no_preference';
export type FundingRequirement = 'full_only' | 'partial_ok' | 'self_fund_possible';

export type AntiGoalKey =
  | 'unpaid_internships'
  | 'non_stem'
  | 'no_funding_info'
  | 'online_only'
  | 'undergrad_only'
  | 'bootcamp'
  | 'other';

export interface IntakeFormData {
  full_name: string;
  email: string;
  nationality_code: string;
  current_country_code: string;
  nationality: string;
  current_country: string;
  linkedin_url: string;
  github_url: string;
  website_url: string;
  google_scholar_url: string;
  orcid: string;

  degree_level: string;
  field_of_study: string;
  field_of_study_other: string;
  institution: string;
  graduation_date: string;
  graduation_month: string;
  graduation_year: string;
  gpa: string;
  gpa_scale: string;
  honors: string;
  honors_other: string;
  english_test: string;
  english_score: string;
  english_test_date: string;
  still_studying: boolean;
  expected_graduation: string;
  current_year: string;

  target_degree: TargetDegree;
  program_styles: string[];
  program_style: ProgramStyle;
  target_intake_term: string;
  custom_intake_term: string;
  funding_requirements: string[];
  funding_requirement: FundingRequirement;
  target_regions: string[];
  target_countries_priority: string[];
  developing_country_scholarships: boolean;
  target_fields: string[];
  research_one_liner: string;
  flagship_projects: string;
  preferred_supervisors: string;
  open_to_ra: boolean;
  fellowship_types: string[];
  anti_goals: AntiGoalKey[];
  anti_goals_other: string;

  target_universities: string;
  connections: string;
  hours_per_week: string;
  search_sources: string[];
  discovery_mode: 'open' | 'target_list';
  open_to_relocation: boolean;
  other_languages: string[];
  mobility_notes: string;
  additional_notes: string;
}

export const DEFAULT_INTAKE_FORM: IntakeFormData = {
  full_name: '',
  email: '',
  nationality_code: '',
  current_country_code: '',
  nationality: '',
  current_country: '',
  linkedin_url: '',
  github_url: '',
  website_url: '',
  google_scholar_url: '',
  orcid: '',

  degree_level: '',
  field_of_study: '',
  field_of_study_other: '',
  institution: '',
  graduation_date: '',
  graduation_month: '',
  graduation_year: '',
  gpa: '',
  gpa_scale: '100',
  honors: '',
  honors_other: '',
  english_test: 'IELTS',
  english_score: '',
  english_test_date: '',
  still_studying: false,
  expected_graduation: '',
  current_year: '',

  target_degree: 'MSc',
  program_styles: ['research_aligned'],
  program_style: 'research_aligned',
  target_intake_term: '',
  custom_intake_term: '',
  funding_requirements: ['full_only'],
  funding_requirement: 'full_only',
  target_regions: [],
  target_countries_priority: [],
  developing_country_scholarships: true,
  target_fields: [],
  research_one_liner: '',
  flagship_projects: '',
  preferred_supervisors: '',
  open_to_ra: false,
  fellowship_types: [],
  anti_goals: ['unpaid_internships', 'non_stem', 'no_funding_info', 'online_only', 'undergrad_only'],
  anti_goals_other: '',

  target_universities: '',
  connections: '',
  hours_per_week: '',
  search_sources: [],
  discovery_mode: 'open',
  open_to_relocation: true,
  other_languages: [],
  mobility_notes: '',
  additional_notes: '',
};

export const FORM_STEPS = [
  { id: 0, label: 'About you' },
  { id: 1, label: 'CV' },
  { id: 2, label: 'Education' },
  { id: 3, label: 'Goals' },
  { id: 4, label: 'Preferences' },
  { id: 5, label: 'Review' },
] as const;

/** @deprecated Use FORM_STEPS — kept for compatibility */
export const WIZARD_STEPS = FORM_STEPS;

export const REGION_OPTIONS = [
  'Germany',
  'Europe',
  'UK',
  'USA',
  'Canada',
  'Australia',
  'Asia',
  'Global',
];

export const FIELD_SUGGESTIONS = [
  'robotics',
  'computer vision',
  'human-robot interaction',
  'machine learning',
  'computational modelling',
  'reinforcement learning',
  'NLP',
  'edge AI',
];

export const ANTI_GOAL_OPTIONS: { key: AntiGoalKey; label: string }[] = [
  { key: 'unpaid_internships', label: 'Unpaid internships / volunteer-only' },
  { key: 'non_stem', label: 'Non-STEM fields' },
  { key: 'no_funding_info', label: 'No funding info for internationals' },
  { key: 'online_only', label: 'Pure online degrees' },
  { key: 'undergrad_only', label: 'Undergraduate-only' },
  { key: 'bootcamp', label: 'Coding bootcamp scholarships' },
];

export interface IntakeDraft {
  step: number;
  form: Partial<IntakeFormData>;
  cv_text: string;
  updated_at?: string;
}

export interface IntakePromptResult {
  prompt: string;
  instructions: string;
  save_path: string;
}

export interface IntakeValidateResult {
  valid: boolean;
  errors: string[];
  profile?: Record<string, unknown>;
  fields_needing_review?: string[];
  confidence?: string;
}

export interface IntakeStatus {
  has_draft: boolean;
  current_step: number;
  has_cv: boolean;
  has_form_answers: boolean;
  has_extraction_output: boolean;
  has_structured_profile: boolean;
  updated_at?: string;
}

export interface IntakeSubmitResult {
  ok: boolean;
  submission_id: string;
  saved_to: string;
}

export function mergeForm(partial?: Partial<IntakeFormData>): IntakeFormData {
  return { ...DEFAULT_INTAKE_FORM, ...partial };
}

/** Map legacy draft keys (pre-refactor wizard) onto the current form shape. */
export function normalizeDraftForm(partial?: Partial<IntakeFormData> & Record<string, unknown>): IntakeFormData {
  const raw = { ...(partial ?? {}) } as Record<string, unknown>;

  if (!raw.nationality_code && raw.nationality) {
    raw.nationality_code = String(raw.nationality);
  }
  if (!raw.current_country_code && raw.current_country) {
    raw.current_country_code = String(raw.current_country);
  }
  if (!raw.graduation_date && (raw.graduation_month || raw.graduation_year)) {
    raw.graduation_date = [raw.graduation_month, raw.graduation_year].filter(Boolean).join(' ');
  }
  if (!raw.target_intake_term && raw.custom_intake_term) {
    raw.target_intake_term = String(raw.custom_intake_term);
  }
  if (Array.isArray(raw.flagship_projects)) {
    raw.flagship_projects = raw.flagship_projects.join(', ');
  }
  if (Array.isArray(raw.target_universities)) {
    raw.target_universities = raw.target_universities.join(', ');
  }
  if (typeof raw.search_sources === 'string') {
    raw.search_sources = parseChipInput(raw.search_sources);
  }
  if (typeof raw.program_styles === 'string' || raw.program_style && !raw.program_styles) {
    const legacy = raw.program_style ?? raw.program_styles;
    raw.program_styles = legacy ? [String(legacy)] : [];
  }
  if (typeof raw.funding_requirements === 'string' || raw.funding_requirement && !raw.funding_requirements) {
    const legacy = raw.funding_requirement ?? raw.funding_requirements;
    raw.funding_requirements = legacy ? [String(legacy)] : [];
  }
  if (typeof raw.target_countries_priority === 'string') {
    raw.target_countries_priority = parseChipInput(raw.target_countries_priority);
  }
  if (typeof raw.other_languages === 'string') {
    raw.other_languages = parseChipInput(raw.other_languages);
  }
  if (typeof raw.hours_per_week === 'number') {
    raw.hours_per_week = String(raw.hours_per_week);
  }

  return mergeForm(raw as Partial<IntakeFormData>);
}

/** Resolve display names and backend-friendly values before API save. */
export function prepareFormPayload(
  form: IntakeFormData,
  countryName: (code: string) => string,
): Record<string, unknown> {
  const intakeTerm =
    form.target_intake_term === 'custom' ? form.custom_intake_term : form.target_intake_term;
  const field =
    form.field_of_study === 'Other' ? form.field_of_study_other : form.field_of_study;
  const honorsVal = form.honors === 'other' ? form.honors_other : form.honors;
  const graduation =
    form.graduation_month && form.graduation_year
      ? `${form.graduation_month} ${form.graduation_year}`
      : form.graduation_date;

  const programStyle = collapseProgramStyle(form.program_styles);
  const fundingReq = collapseFundingRequirement(form.funding_requirements);

  return {
    ...form,
    nationality: countryName(form.nationality_code) || form.nationality,
    current_country: countryName(form.current_country_code) || form.current_country,
    target_intake_term: intakeTerm,
    field_of_study: field,
    honors: honorsVal,
    graduation_date: graduation,
    program_style: programStyle,
    program_styles: form.program_styles,
    funding_requirement: fundingReq,
    funding_requirements: form.funding_requirements,
    target_countries_priority: form.target_countries_priority,
  };
}

/** Collapse multi-select program styles to single L2 enum value. */
export function collapseProgramStyle(styles: string[]): ProgramStyle {
  if (!styles.length || styles.includes('no_preference')) {
    return 'no_preference';
  }
  const hasResearch = styles.includes('research_aligned');
  const hasCoursework = styles.includes('coursework');
  if (hasResearch && hasCoursework) {
    return 'no_preference';
  }
  if (hasResearch) return 'research_aligned';
  if (hasCoursework) return 'coursework';
  return 'no_preference';
}

/** Collapse multi-select funding to strictest single L2 value. */
export function collapseFundingRequirement(reqs: string[]): FundingRequirement {
  const order: FundingRequirement[] = ['full_only', 'partial_ok', 'self_fund_possible'];
  for (const r of order) {
    if (reqs.includes(r)) return r;
  }
  return 'full_only';
}

export function parseChipInput(value: string): string[] {
  return value
    .split(/[,;\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function chipsToInput(values: string[]): string {
  return values.join(', ');
}
