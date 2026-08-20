import type { Opportunity, DeadlineBucket } from '../api/client';

export function deadlineChipClass(bucket?: DeadlineBucket): string {
  switch (bucket) {
    case 'overdue':
      return 'deadline-overdue';
    case 'today':
      return 'deadline-today';
    case 'within_3_days':
      return 'deadline-urgent';
    case 'within_7_days':
      return 'deadline-soon';
    case 'within_30_days':
      return 'deadline-later';
    case 'unknown':
      return 'deadline-unknown';
    default:
      return 'deadline-later';
  }
}

export function deadlineChipLabel(opportunity: Opportunity): string | null {
  if (opportunity.deadline_bucket === 'unknown') {
    return 'Deadline not confirmed';
  }
  return opportunity.urgency_label ?? null;
}

export function hasCalendarDeadline(opportunity: Opportunity): boolean {
  return Boolean(opportunity.deadline) && opportunity.deadline_bucket !== 'unknown';
}
