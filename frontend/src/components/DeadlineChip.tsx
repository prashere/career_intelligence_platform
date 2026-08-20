import type { ReactNode } from 'react';

export function DeadlineChip({
  label,
  className = '',
}: {
  label: string;
  className?: string;
}) {
  return <span className={`opp-deadline-chip ${className}`.trim()}>{label}</span>;
}

export {
  deadlineChipClass,
  deadlineChipLabel,
  hasCalendarDeadline,
} from './deadlineChipUtils';
