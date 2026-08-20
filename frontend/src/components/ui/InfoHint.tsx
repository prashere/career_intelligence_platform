import { ReactNode } from 'react';

function InfoIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.75" />
      <path d="M12 10v6M12 7h.01" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

export function InfoHint({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <span className="hint-popover-wrap scheduler-info-hint">
      <button type="button" className="hint-popover-trigger scheduler-info-trigger" aria-label={label}>
        <InfoIcon />
      </button>
      <div className="hint-popover scheduler-info-popover" role="tooltip">
        <p className="hint-popover-title">{label}</p>
        <div className="scheduler-info-body">{children}</div>
      </div>
    </span>
  );
}
