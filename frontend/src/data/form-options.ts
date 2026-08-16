/** Curated form option lists for intake wizard. */

export const DEGREE_LEVELS = [
  'High School / A-Levels',
  'Associate / Diploma',
  'BSc / BA / BE',
  'BEng',
  'MSc / MA / MS',
  'MEng',
  'PhD',
  'Other',
] as const;

export const STUDY_FIELDS = [
  'Computer Science',
  'Artificial Intelligence',
  'Robotics',
  'Electrical Engineering',
  'Mechanical Engineering',
  'Data Science',
  'Computational Modelling',
  'Human-Computer Interaction',
  'Cognitive Science',
  'Mathematics',
  'Physics',
  'Biomedical Engineering',
  'Other',
] as const;

export const HONORS_OPTIONS = [
  { value: '', label: 'None / not applicable' },
  { value: 'First Class Honours', label: 'First Class Honours' },
  { value: 'Upper Second (2:1)', label: 'Upper Second (2:1)' },
  { value: 'Lower Second (2:2)', label: 'Lower Second (2:2)' },
  { value: 'Summa cum laude', label: 'Summa cum laude' },
  { value: 'Magna cum laude', label: 'Magna cum laude' },
  { value: 'Cum laude', label: 'Cum laude' },
  { value: 'Distinction', label: 'Distinction' },
  { value: 'Dean\'s List', label: "Dean's List" },
  { value: 'other', label: 'Other (type below)' },
] as const;

export const GPA_SCALES = [
  { value: '4.0', label: '4.0 scale (US-style)' },
  { value: '100', label: 'Percentage (0 to 100)' },
  { value: '10', label: '10-point scale' },
  { value: 'UK', label: 'UK classification' },
  { value: 'other', label: 'Other' },
] as const;

export const INTAKE_TERMS = [
  'Fall 2026',
  'Spring 2027',
  'Fall 2027',
  'Spring 2028',
  'Fall 2028',
  'Flexible / rolling',
  'custom',
] as const;

export const ENGLISH_TESTS = [
  { value: 'IELTS', label: 'IELTS' },
  { value: 'TOEFL', label: 'TOEFL iBT' },
  { value: 'Duolingo', label: 'Duolingo English Test' },
  { value: 'PTE', label: 'PTE Academic' },
  { value: 'Exempt', label: 'Exempt (native / prior degree in English)' },
  { value: 'None', label: 'Not taken yet' },
  { value: 'Other', label: 'Other' },
] as const;

export const FELLOWSHIP_TYPES = [
  'Research fellowship',
  'Leadership / policy',
  'Country-specific (DAAD, Chevening, etc.)',
  'Industry-sponsored',
  'Postdoctoral',
] as const;

export const STUDY_YEARS = ['1st year', '2nd year', '3rd year', '4th year', 'Final year'] as const;

export const PROGRAM_STYLE_OPTIONS = [
  { value: 'research_aligned', label: 'Research-aligned (thesis / lab)' },
  { value: 'coursework', label: 'Coursework-heavy' },
  { value: 'no_preference', label: 'No strong preference' },
] as const;

export const FUNDING_REQUIREMENT_OPTIONS = [
  { value: 'full_only', label: 'Fully funded only' },
  { value: 'partial_ok', label: 'Partial funding OK' },
  { value: 'self_fund_possible', label: 'Self-fund possible' },
] as const;

export const OTHER_LANGUAGE_OPTIONS = [
  'German',
  'French',
  'Spanish',
  'Italian',
  'Dutch',
  'Mandarin',
  'Japanese',
  'Arabic',
  'Hindi',
] as const;

/** Common priority countries for chip picker (names match filter region aliases). */
export const PRIORITY_COUNTRY_CHIPS = [
  'Germany',
  'United Kingdom',
  'United States',
  'Canada',
  'Australia',
  'Netherlands',
  'Switzerland',
  'France',
  'Sweden',
  'Norway',
  'Japan',
  'Singapore',
] as const;

export const DISCOVERY_MODE_OPTIONS = [
  { value: 'open', label: 'Open discovery, show best funded matches anywhere' },
  { value: 'target_list', label: 'Focus on specific universities I list' },
] as const;

export const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const;

export function graduationYears(): number[] {
  const current = new Date().getFullYear();
  return Array.from({ length: 12 }, (_, i) => current - 4 + i);
}

export const SEARCH_SOURCE_OPTIONS = [
  'Scholars4Dev',
  'DAAD',
  'ProFellow',
  'University websites',
  'LinkedIn',
  'FindAPhD / MastersPortal',
  'Professor cold emails',
  'Twitter / X academic',
] as const;
