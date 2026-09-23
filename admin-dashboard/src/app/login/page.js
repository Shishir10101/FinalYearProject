'use client';
import { useState } from 'react';
import { useAdmin } from '@/context/AdminContext';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAdmin();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const result = await login(username, password);
      if (!result.ok) setError(result.error);
    } catch (err) {
      setError('Could not reach the server. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '80vh' }}>
      <div className="card" style={{ width: '400px', padding: '40px' }}>
        <h2 style={{ textAlign: 'center', marginBottom: '8px', color: 'var(--primary)' }}>
          Admin Login
        </h2>
        <p style={{ textAlign: 'center', color: 'var(--text-gray)', fontSize: '0.9rem', marginBottom: '24px' }}>
          Sign in to manage the store
        </p>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="username" style={{ display: 'block', marginBottom: '5px', fontWeight: 600, fontSize: '0.9rem' }}>
              Username
            </label>
            <input
              id="username"
              type="text"
              className="search-input"
              style={{ width: '100%' }}
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label htmlFor="password" style={{ display: 'block', marginBottom: '5px', fontWeight: 600, fontSize: '0.9rem' }}>
              Password
            </label>
            <input
              id="password"
              type="password"
              className="search-input"
              style={{ width: '100%' }}
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <p role="alert" style={{ color: '#c62828', marginBottom: '12px', fontSize: '0.9rem' }}>
              {error}
            </p>
          )}

          <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={submitting}>
            {submitting ? 'Signing in…' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  );
}
