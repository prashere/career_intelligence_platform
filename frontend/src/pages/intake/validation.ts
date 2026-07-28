import { IntakeFormData } from '../../types/intake';

export function getStepErrors(step: number, form: IntakeFormData, cvText: string): string[] {
  const errors: string[] = [];
  switch (step) {
    case 0:
      if (!form.full_name.trim()) errors.push('Enter your full name');
      if (!form.nationality_code) errors.push('Select your nationality');
      if (!form.linkedin_url.trim()) errors.push('Add your LinkedIn URL');
      break;
    case 1:
      if (cvText.trim().length < 100) {
        errors.push(`CV needs at least 100 characters (${cvText.trim().length} so far)`);
      }
      break;
    case 2:
      if (!form.degree_level) errors.push('Select your degree level');
      if (!form.field_of_study) errors.push('Select your field of study');
      if (form.field_of_study === 'Other' && !form.field_of_study_other.trim()) {
        errors.push('Specify your field of study');
      }
      if (!form.institution.trim()) errors.push('Enter your institution');
      break;
    case 3:
      if (!form.target_intake_term) errors.push('Select a target intake');
      if (form.target_intake_term === 'custom' && !form.custom_intake_term.trim()) {
        errors.push('Specify your target intake term');
      }
      if (form.target_regions.length < 1) errors.push('Select at least one region');
      if (form.target_fields.length < 3) {
        errors.push(`Select at least 3 research areas (${form.target_fields.length}/3)`);
      }
      break;
    default:
      break;
  }
  return errors;
}

export function canProceed(step: number, form: IntakeFormData, cvText: string): boolean {
  return getStepErrors(step, form, cvText).length === 0;
}
