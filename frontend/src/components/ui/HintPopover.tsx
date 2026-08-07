import { ReactNode } from 'react';

function EnvelopeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M3 8l8.5 6L20 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function HintPopover({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <span className="hint-popover-wrap">
      <button type="button" className="hint-popover-trigger" aria-label={label}>
        <EnvelopeIcon />
      </button>
      <div className="hint-popover" role="tooltip">
        <p className="hint-popover-title">{label}</p>
        {children}
      </div>
    </span>
  );
}
