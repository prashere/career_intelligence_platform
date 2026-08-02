import { useState } from 'react';
import { NavLink } from 'react-router-dom';

export const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', end: true as const },
  { to: '/profile', label: 'Profile', end: false as const },
  { to: '/profile/setup', label: 'Profile setup', end: false as const },
] as const;

interface SidebarNavProps {
  onNavigate?: () => void;
}

export function SidebarNav({ onNavigate }: SidebarNavProps) {
  return (
    <nav className="sidebar-nav" aria-label="Main">
      {NAV_ITEMS.map(({ to, label, ...rest }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          onClick={onNavigate}
          {...rest}
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="app-shell">
      <aside className={`sidebar${mobileOpen ? ' open' : ''}`}>
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            CI
          </span>
          <div>
            <h1>Career Intelligence</h1>
            {/* <p className="brand-tagline">Funded opportunities, matched to you</p> */}
          </div>
        </div>
        <SidebarNav onNavigate={() => setMobileOpen(false)} />
        <footer className="sidebar-footer">
          <NavLink to="/profile/setup" className="sidebar-cta" onClick={() => setMobileOpen(false)}>
            Complete profile setup →
          </NavLink>
        </footer>
      </aside>

      {mobileOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close menu"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <div className="app-main">
        <header className="topbar">
          <button
            type="button"
            className="menu-toggle"
            aria-expanded={mobileOpen}
            aria-label="Open menu"
            onClick={() => setMobileOpen((o) => !o)}
          >
            <span />
            <span />
            <span />
          </button>
          <span className="topbar-title">Career Intelligence</span>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
