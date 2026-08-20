function CalendarFileIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M8 2v3M16 2v3M4 9h16M6 5h12a2 2 0 012 2v13a2 2 0 01-2 2H6a2 2 0 01-2-2V7a2 2 0 012-2z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M8 13h4v4H8v-4z" fill="currentColor" opacity="0.35" />
    </svg>
  );
}

function GoogleCalendarIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
      <rect x="3" y="4" width="18" height="17" rx="2" fill="#fff" stroke="currentColor" strokeWidth="1.5" />
      <rect x="3" y="4" width="18" height="5" fill="#4285F4" />
      <text x="7" y="17" fill="#4285F4" fontSize="9" fontWeight="700" fontFamily="Arial,sans-serif">31</text>
    </svg>
  );
}

interface Props {
  disabled?: boolean;
  onDownloadIcs: () => void;
  onGoogleCalendar: () => void;
}

export default function CardCalendarActions({
  disabled = false,
  onDownloadIcs,
  onGoogleCalendar,
}: Props) {
  return (
    <div className="opp-calendar-actions" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className="opp-calendar-btn opp-calendar-btn-ics"
        disabled={disabled}
        aria-label="Download calendar file (.ics)"
        onClick={onDownloadIcs}
      >
        <CalendarFileIcon />
        <span className="opp-calendar-btn-text">Download .ics</span>
      </button>
      <button
        type="button"
        className="opp-calendar-btn opp-calendar-btn-icon"
        disabled={disabled}
        aria-label="Add to Google Calendar"
        onClick={onGoogleCalendar}
      >
        <GoogleCalendarIcon />
        <span className="opp-calendar-tooltip">Add to Google Calendar</span>
      </button>
    </div>
  );
}
