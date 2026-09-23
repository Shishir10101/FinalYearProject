'use client';
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { api } from '@/lib/api';

const AdminContext = createContext(null);

const TOKEN_KEY = 'admin_token';
const PUBLIC_PATHS = ['/login'];

/**
 * Roles that may open the dashboard at all. Mirrors `core.permissions.STAFF_ROLES`
 * — a vendor belongs here, which is the whole point of the role.
 */
const STAFF_ROLES = ['super_admin', 'admin', 'vendor'];

export function AdminProvider({ children }) {
  const [isAdmin, setIsAdmin] = useState(false);
  const [user, setUser] = useState(null);
  const [role, setRole] = useState(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  // Verify the stored token against the API rather than trusting its presence.
  // The server is the authority on whether this account may use the dashboard.
  const verify = useCallback(async () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem(TOKEN_KEY) : null;

    if (!token) {
      setIsAdmin(false);
      setUser(null);
      setRole(null);
      setLoading(false);
      return false;
    }

    try {
      const data = await api.get('/auth/profile/');
      const profile = data?.profile || {};
      // The gate is the **resolved role**, which the API computes through
      // `core.permissions.get_role`. It used to be `is_admin_user` — a legacy
      // boolean that `UserProfile.save()` only ever sets for super_admin/admin.
      // A vendor therefore had a correctly scoped API and no way in: the token
      // verified, `allowed` came back false, the token was discarded and the
      // login bounced straight back to this page. The VENDOR role existed on the
      // server and was unreachable in the product.
      const resolvedRole = profile.role || null;
      const allowed = STAFF_ROLES.includes(resolvedRole);
      setIsAdmin(allowed);
      setUser(data);
      // The role drives which navigation items and write controls are shown.
      // It is informational only — the server enforces every permission.
      setRole(resolvedRole);
      if (!allowed) {
        localStorage.removeItem(TOKEN_KEY);
      }
      return allowed;
    } catch (e) {
      localStorage.removeItem(TOKEN_KEY);
      setIsAdmin(false);
      setUser(null);
      setRole(null);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ok = await verify();
      if (cancelled) return;
      if (!ok && !PUBLIC_PATHS.includes(pathname)) {
        router.replace('/login');
      }
    })();
    return () => { cancelled = true; };
  }, [pathname, router, verify]);

  const login = async (username, password) => {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api'}/auth/login/`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      }
    );

    if (!res.ok) {
      return { ok: false, error: 'Invalid username or password.' };
    }

    const data = await res.json();
    if (typeof window !== 'undefined') {
      localStorage.setItem(TOKEN_KEY, data.access);
    }

    const allowed = await verify();

    if (!allowed) {
      return {
        ok: false,
        error: 'This account does not have dashboard access.',
      };
    }

    router.replace('/');
    return { ok: true };
  };

  const logout = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(TOKEN_KEY);
    }
    setIsAdmin(false);
    setUser(null);
    setRole(null);
    router.replace('/login');
  };

  // Managers run the shop; a vendor only manages their own catalogue.
  const isManager = role === 'super_admin' || role === 'admin';

  return (
    <AdminContext.Provider
      value={{ isAdmin, isManager, role, user, loading, login, logout, refresh: verify }}
    >
      {children}
    </AdminContext.Provider>
  );
}

export const useAdmin = () => useContext(AdminContext);
