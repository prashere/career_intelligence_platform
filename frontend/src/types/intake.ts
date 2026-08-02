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
  nationality: string;
  current_country: string;
  linkedin_url: string;
  github_url: string;
  website_url: string;

  degree_level: string;
  field_of_study: string;
  institution: string;
  graduation_date: string;
  gpa: string;
  honors: string;
  english_test: string;
  english_score: string;
  english_test_date: string;
  still_studying: boolean;
  expected_graduation: string;
  current_year: string;

  target_degree: TargetDegree;
  program_style: ProgramStyle;
  target_intake_term: string;
  funding_requirement: FundingRequirement;
  target_regions: string[];
  target_countries_priority: string;
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
  search_sources: string;
  additional_notes: string;
}

export const DEFAULT_INTAKE_FORM: IntakeFormData = {
  full_name: '',
  nationality: '',
  current_country: '',
  linkedin_url: '',
  github_url: '',
  website_url: '',

  degree_level: '',
  field_of_study: '',
  institution: '',
  graduation_date: '',
  gpa: '',
  honors: '',
  english_test: 'IELTS',
  english_score: '',
  english_test_date: '',
  still_studying: false,
  expected_graduation: '',
  current_year: '',

  target_degree: 'MSc',
  program_style: 'research_aligned',
  target_intake_term: '',
  funding_requirement: 'full_only',
  target_regions: [],
  target_countries_priority: '',
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
  search_sources: '',
  additional_notes: '',
};

export const WIZARD_STEPS = [
  { id: 0, label: 'Identity', group: 'form' },
  { id: 1, label: 'CV', group: 'form' },
  { id: 2, label: 'Education', group: 'form' },
  { id: 3, label: 'Goals', group: 'form' },
  { id: 4, label: 'Optional', group: 'form' },
  { id: 5, label: 'Review', group: 'form' },
  { id: 6, label: 'Pass 1 prompt', group: 'llm' },
  { id: 7, label: 'Validate JSON', group: 'llm' },
  { id: 8, label: 'Pass 2 prompt', group: 'llm' },
] as const;

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

export function mergeForm(partial?: Partial<IntakeFormData>): IntakeFormData {
  return { ...DEFAULT_INTAKE_FORM, ...partial };
}

/** Map legacy draft keys (pre-refactor wizard) onto the current form shape. */
export function normalizeDraftForm(partial?: Partial<IntakeFormData> & Record<string, unknown>): IntakeFormData {
  const raw = { ...(partial ?? {}) } as Record<string, unknown>;

  if (!raw.nationality && raw.nationality_code) {
    raw.nationality = String(raw.nationality_code);
  }
  if (!raw.current_country && raw.current_country_code) {
    raw.current_country = String(raw.current_country_code);
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
  if (Array.isArray(raw.search_sources)) {
    raw.search_sources = raw.search_sources.join(', ');
  }
  if (typeof raw.hours_per_week === 'number') {
    raw.hours_per_week = String(raw.hours_per_week);
  }

  return mergeForm(raw as Partial<IntakeFormData>);
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
