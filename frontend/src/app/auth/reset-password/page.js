'use client';
import { useState, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { authAPI } from '@/lib/api';
import styles from '../auth.module.css';

/** Turn a DRF error payload into one message per field. */
function readFieldErrors(err) {
  const fields = err?.fields || {};
  const out = {};
  Object.entries(fields).forEach(([key, value]) => {
    out[key] = Array.isArray(value) ? value.join(' ') : String(value);
  });
  return out;
}

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const uid = searchParams.get('uid') || '';
  const token = searchParams.get('token') || '';

  const [form, setForm] = useState({ new_password: '', new_password2: '' });
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');

  const linkIncomplete = !uid || !token;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setFieldErrors({});
    try {
      await authAPI.confirmPasswordReset({ uid, token, ...form });
      setDone(true);
    } catch (err) {
      const fields = readFieldErrors(err);
      setFieldErrors(fields);
      // Surface a general message only when nothing was attributed to a field,
      // so the customer is never told "invalid" twice for one problem.
      if (Object.keys(fields).length === 0) {
        setError(err.message || 'Could not reset your password. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  if (linkIncomplete) {
    return (
      <div className={styles.authContainer}>
        <div className={styles.authCard}>
          <div className={styles.authHeader}>
            <h2>Reset Password</h2>
          </div>
          <div className={styles.notice} role="alert">
            This page needs a valid reset link. Open the link from your email, or
            request a new one.
          </div>
          <div className={styles.authFooter}>
            <p>
              <Link href="/auth/forgot-password">Request a new link</Link>
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className={styles.authContainer}>
        <div className={styles.authCard}>
          <div className={styles.authHeader}>
            <h2>Password Updated</h2>
            <p>You can now sign in with your new password.</p>
          </div>
          <Link
            href="/auth/login"
            className="btn btn-primary"
            style={{ width: '100%', display: 'block', textAlign: 'center' }}
          >
            Go to login
          </Link>
        </div>
      </div>
    );
  }

  // A dead link cannot be fixed by retyping a password, so the form is hidden
  // rather than left on screen to fail again.
  if (fieldErrors.token) {
    return (
      <div className={styles.authContainer}>
        <div className={styles.authCard}>
          <div className={styles.authHeader}>
            <h2>Link Expired</h2>
          </div>
          <div className={styles.notice} role="alert">
            {fieldErrors.token}
          </div>
          <div className={styles.authFooter}>
            <p>
              <Link href="/auth/forgot-password">Request a new link</Link>
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.authContainer}>
      <div className={styles.authCard}>
        <div className={styles.authHeader}>
          <h2>Choose a New Password</h2>
          <p>Pick something you have not used before</p>
        </div>

        <form onSubmit={handleSubmit} className={styles.authForm}>
          <div className="form-group">
            <label className="form-label" htmlFor="new-password">
              New password
            </label>
            <input
              id="new-password"
              type="password"
              className="form-input"
              value={form.new_password}
              onChange={(e) => setForm({ ...form, new_password: e.target.value })}
              autoComplete="new-password"
              required
            />
            {fieldErrors.new_password && (
              <p className={styles.fieldError} role="alert">{fieldErrors.new_password}</p>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="confirm-password">
              Confirm new password
            </label>
            <input
              id="confirm-password"
              type="password"
              className="form-input"
              value={form.new_password2}
              onChange={(e) => setForm({ ...form, new_password2: e.target.value })}
              autoComplete="new-password"
              required
            />
            {fieldErrors.new_password2 && (
              <p className={styles.fieldError} role="alert">{fieldErrors.new_password2}</p>
            )}
          </div>

          {error && <p className={styles.fieldError} role="alert">{error}</p>}

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%' }}
            disabled={loading}
          >
            {loading ? 'Saving…' : 'Set new password'}
          </button>
        </form>

        <div className={styles.authFooter}>
          <p>
            <Link href="/auth/login">Back to login</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  // useSearchParams must sit inside <Suspense> or the production build fails.
  return (
    <Suspense fallback={<div className="container section text-center">Loading…</div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
