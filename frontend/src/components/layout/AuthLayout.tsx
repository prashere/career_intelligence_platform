import { ReactNode } from 'react';

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="auth-shell">
      <div className="auth-panel auth-panel-brand">
        <div className="auth-brand-link">
          <span className="auth-brand-mark" aria-hidden>
            CI
          </span>
          <span className="auth-brand-name">Career Intelligence</span>
        </div>
        <p className="auth-brand-tagline">
          Discover funded opportunities matched to your profile, goals, and timeline.
        </p>
      </div>

      <div className="auth-panel auth-panel-form">
        <div className="auth-form-wrap">
          <header className="auth-form-header">
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </header>
          {children}
          <footer className="auth-form-footer">{footer}</footer>
        </div>
      </div>
    </div>
  );
}
