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
  linkedin_url: string;
  github_url: string;
  website_url: string;
  google_scholar_url: string;
  orcid: string;

  degree_level: string;
  field_of_study: string;
  field_of_study_other: string;
  institution: string;
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
  program_style: ProgramStyle;
  target_intake_term: string;
  custom_intake_term: string;
  funding_requirement: FundingRequirement;
  target_regions: string[];
  target_countries_priority: string[];
  developing_country_scholarships: boolean;
  target_fields: string[];
  research_one_liner: string;
  flagship_projects: string[];
  preferred_supervisors: string;
  open_to_ra: boolean;
  fellowship_types: string[];
  anti_goals: AntiGoalKey[];
  anti_goals_other: string;

  target_universities: string[];
  connections: string;
  hours_per_week: number | '';
  search_sources: string[];
  additional_notes: string;
}

export const DEFAULT_INTAKE_FORM: IntakeFormData = {
  full_name: '',
  email: '',
  nationality_code: '',
  current_country_code: '',
  linkedin_url: '',
  github_url: '',
  website_url: '',
  google_scholar_url: '',
  orcid: '',

  degree_level: '',
  field_of_study: '',
  field_of_study_other: '',
  institution: '',
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
  program_style: 'research_aligned',
  target_intake_term: 'Fall 2027',
  custom_intake_term: '',
  funding_requirement: 'full_only',
  target_regions: [],
  target_countries_priority: [],
  developing_country_scholarships: true,
  target_fields: [],
  research_one_liner: '',
  flagship_projects: [],
  preferred_supervisors: '',
  open_to_ra: false,
  fellowship_types: [],
  anti_goals: ['unpaid_internships', 'non_stem', 'no_funding_info', 'online_only', 'undergrad_only'],
  anti_goals_other: '',

  target_universities: [],
  connections: '',
  hours_per_week: '',
  search_sources: [],
  additional_notes: '',
};

export const WIZARD_STEPS = [
  { id: 0, label: 'About you' },
  { id: 1, label: 'CV' },
  { id: 2, label: 'Education' },
  { id: 3, label: 'Goals' },
  { id: 4, label: 'Preferences' },
  { id: 5, label: 'Review' },
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
  'social robotics',
  'adaptive systems',
];

export const ANTI_GOAL_OPTIONS: { key: AntiGoalKey; label: string }[] = [
  { key: 'unpaid_internships', label: 'Unpaid / volunteer-only' },
  { key: 'non_stem', label: 'Non-STEM' },
  { key: 'no_funding_info', label: 'No funding clarity' },
  { key: 'online_only', label: 'Online-only degrees' },
  { key: 'undergrad_only', label: 'Undergraduate-only' },
  { key: 'bootcamp', label: 'Bootcamp scholarships' },
];

export interface IntakeDraft {
  step: number;
  form: Partial<IntakeFormData>;
  cv_text: string;
  updated_at?: string;
}

export interface IntakeSubmitResult {
  ok: boolean;
  saved_to: string;
  submitted_at: string;
  submission_id: string;
}

export function mergeForm(partial?: Partial<IntakeFormData>): IntakeFormData {
  return { ...DEFAULT_INTAKE_FORM, ...partial };
}
