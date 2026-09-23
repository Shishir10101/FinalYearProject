'use client';
import { useState } from 'react';
import Link from 'next/link';
import { authAPI } from '@/lib/api';
import styles from '../auth.module.css';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await authAPI.requestPasswordReset(email.trim());
      setResult(data);
    } catch (err) {
      // The backend deliberately does not distinguish a known address from an
      // unknown one, so the only failures reaching here are validation or
      // transport problems.
      const fieldError = err.fields?.email;
      setError(
        (Array.isArray(fieldError) ? fieldError.join(' ') : fieldError)
          || err.message
          || 'Something went wrong. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.authContainer}>
      <div className={styles.authCard}>
        <div className={styles.authHeader}>
          <h2>Forgot Password</h2>
          <p>We will email you a link to choose a new password</p>
        </div>

        {result ? (
          <>
            <div className={styles.notice} role="status">
              {result.message}
            </div>

            {result.reset_url && (
              <div className={styles.devNotice}>
                <strong>Development build</strong>
                <p>
                  No mailbox is configured here, so the link is shown directly
                  instead of being emailed:
                </p>
                <Link href={result.reset_url.replace(/^https?:\/\/[^/]+/, '')}>
                  Open the reset link
                </Link>
                <p className={styles.devNote}>
                  This never appears in a real deployment.
                </p>
              </div>
            )}

            <div className={styles.authFooter}>
              <p>
                Remembered it? <Link href="/auth/login">Back to login</Link>
              </p>
            </div>
          </>
        ) : (
          <>
            <form onSubmit={handleSubmit} className={styles.authForm}>
              <div className="form-group">
                <label className="form-label" htmlFor="reset-email">
                  Email address
                </label>
                <input
                  id="reset-email"
                  type="email"
                  className="form-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>

              {error && <p className={styles.fieldError} role="alert">{error}</p>}

              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: '100%' }}
                disabled={loading}
              >
                {loading ? 'Sending…' : 'Send reset link'}
              </button>
            </form>

            <div className={styles.authFooter}>
              <p>
                Remembered it? <Link href="/auth/login">Back to login</Link>
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
