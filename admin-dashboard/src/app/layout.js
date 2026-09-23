'use client';
import { useEffect, useState } from 'react';
import { AdminProvider, useAdmin } from '@/context/AdminContext';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import './globals.css';

// `managerOnly` items are hidden from vendors. Hiding them is a courtesy, not a
// security boundary — every one of these routes is also enforced server-side.
const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: '📊' },
  { href: '/products', label: 'Products', icon: '📦' },
  { href: '/orders', label: 'Orders', icon: '🛒' },
  { href: '/festivals', label: 'Festival Kits', icon: '🎉', managerOnly: true },
  { href: '/pujas', label: 'Rituals', icon: '🪔', managerOnly: true },
  { href: '/vendors', label: 'Vendors', icon: '🏪', managerOnly: true },
  { href: '/reviews', label: 'Reviews', icon: '⭐', managerOnly: true },
  { href: '/forecast', label: 'Demand Forecast', icon: '📈' },
  { href: '/settings', label: 'Catalog Settings', icon: '⚙️', managerOnly: true },
];

const ROLE_LABELS = {
  super_admin: 'Super Admin',
  admin: 'Administrator',
  vendor: 'Vendor',
  customer: 'Customer',
};

function Sidebar({ onNavigate }) {
  const pathname = usePathname();
  const { logout, user, isAdmin, isManager, role } = useAdmin();

  // Never show navigation to an unauthenticated visitor.
  if (pathname === '/login' || !isAdmin) return null;

  const items = NAV_ITEMS.filter((item) => !item.managerOnly || isManager);

  return (
    <div className="sidebar">
      <h2 style={{ color: 'var(--primary)', marginBottom: '30px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span>🪔</span> Admin Panel
      </h2>

      <nav>
        {items.map(item => (
          <Link
            key={item.href}
            href={item.href}
            className={pathname === item.href ? 'active' : ''}
            onClick={onNavigate}
          >
            {item.icon} {item.label}
          </Link>
        ))}
      </nav>

      <div style={{ position: 'absolute', bottom: '20px', width: 'calc(100% - 40px)' }}>
        {user && (
          <div style={{ marginBottom: '12px', fontSize: '0.8rem', color: 'var(--text-gray)' }}>
            Signed in as
            <div style={{ fontWeight: 600, color: 'var(--text-dark)' }}>
              {user.first_name || user.username}
            </div>
            {role && (
              <span className="badge badge-neutral" style={{ marginTop: '4px' }}>
                {ROLE_LABELS[role] || role}
              </span>
            )}
          </div>
        )}
        <button
          className="btn"
          style={{ width: '100%', background: '#ffeded', color: 'var(--primary)' }}
          onClick={logout}
        >
          Logout
        </button>
      </div>
    </div>
  );
}

/**
 * Below 880px the fixed 250px sidebar would leave a phone with almost no usable
 * width, so it becomes an off-canvas drawer. The toggle only exists in that
 * range (see .nav-toggle / .sidebar in globals.css) but is harmless on desktop.
 */
function NavShell({ children }) {
  const pathname = usePathname();
  const { isAdmin } = useAdmin();
  const [open, setOpen] = useState(false);

  // Close the drawer whenever the route changes.
  useEffect(() => { setOpen(false); }, [pathname]);

  // Escape closes it, matching the Modal component's behaviour.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (pathname === '/login' || !isAdmin) return children;

  return (
    <>
      <button
        type="button"
        className="nav-toggle"
        aria-label={open ? 'Close navigation' : 'Open navigation'}
        aria-expanded={open}
        aria-controls="admin-sidebar"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? '✕' : '☰'}
      </button>

      {open && (
        <div
          className="nav-scrim"
          role="presentation"
          onClick={() => setOpen(false)}
        />
      )}

      <div id="admin-sidebar" className={open ? 'nav-open' : ''}>
        <Sidebar onNavigate={() => setOpen(false)} />
      </div>

      {children}
    </>
  );
}

/** Blocks protected content until the token has been verified against the API. */
function AuthGate({ children }) {
  const pathname = usePathname();
  const { isAdmin, loading } = useAdmin();

  if (pathname === '/login') return children;

  if (loading || !isAdmin) {
    return (
      <div className="state-inline" style={{ marginTop: '80px' }}>
        {loading ? 'Checking your session…' : 'Redirecting to login…'}
      </div>
    );
  }

  return children;
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AdminProvider>
          <div className="dashboard-layout">
            <NavShell>
              <div className="main-content">
                <AuthGate>{children}</AuthGate>
              </div>
            </NavShell>
          </div>
        </AdminProvider>
      </body>
    </html>
  );
}
