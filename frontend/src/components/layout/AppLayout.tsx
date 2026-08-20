import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../ui/Primitives';

const BASE_NAV = [
  { to: '/', label: 'Dashboard', end: true as const },
  { to: '/profile', label: 'Profile', end: false as const },
  { to: '/profile/setup', label: 'Profile setup', end: false as const },
] as const;

interface SidebarNavProps {
  onNavigate?: () => void;
}

export function SidebarNav({ onNavigate }: SidebarNavProps) {
  const { isAdmin } = useAuth();
  const items = isAdmin
    ? [
        ...BASE_NAV,
        { to: '/admin/sources', label: 'Sources', end: false as const },
        { to: '/admin/ingestion', label: 'Ingestion', end: false as const },
        { to: '/admin/ingestion/playground', label: 'Ingestion lab', end: false as const },
        { to: '/admin/schedulers', label: 'Background tasks', end: false as const },
      ]
    : BASE_NAV;

  return (
    <nav className="sidebar-nav" aria-label="Main">
      {items.map(({ to, label, ...rest }) => (
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

function userInitials(name?: string | null, email?: string): string {
  if (name?.trim()) {
    const parts = name.trim().split(/\s+/);
    return parts.length >= 2
      ? `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
      : parts[0].slice(0, 2).toUpperCase();
  }
  return (email?.[0] ?? '?').toUpperCase();
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, logout, isAdmin } = useAuth();
  const displayName = user?.name?.trim() || user?.email?.split('@')[0] || 'Account';

  return (
    <div className="app-shell">
      <aside className={`sidebar${mobileOpen ? ' open' : ''}`}>
        <div className="sidebar-brand">
          <div className="brand">
            <span className="brand-mark" aria-hidden>
              CI
            </span>
            <div>
              <h1>Career Intelligence</h1>
            </div>
          </div>
        </div>

        <div className="sidebar-nav-wrap">
          <SidebarNav onNavigate={() => setMobileOpen(false)} />
        </div>

        <footer className="sidebar-footer">
          <div className="sidebar-user-card">
            <span className="sidebar-avatar" aria-hidden>
              {userInitials(user?.name, user?.email)}
            </span>
            <div className="sidebar-user-meta">
              <p className="sidebar-user-name">{displayName}</p>
              <p className="sidebar-user-email">{user?.email}</p>
              {isAdmin && <span className="badge badge-admin">Admin</span>}
            </div>
          </div>
          <Button variant="ghost" className="sidebar-logout" onClick={logout}>
            Sign out
          </Button>
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
