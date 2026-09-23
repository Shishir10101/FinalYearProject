'use client';
import { useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import styles from '../auth.module.css';

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { register, login } = useAuth();
  const { success, error } = useToast();

  const [formData, setFormData] = useState({ 
    username: '', 
    email: '',
    password: '',
    password2: '',
    first_name: '',
    last_name: '',
    phone: '',
    city: 'kathmandu'
  });
  const [loading, setLoading] = useState(false);

  const redirect = searchParams.get('redirect') || '/';

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (formData.password !== formData.password2) {
      error("Passwords do not match");
      return;
    }

    setLoading(true);
    try {
      await register(formData);
      // Auto login after register
      await login(formData.username, formData.password);
      success("Registration successful");
      router.push(redirect);
    } catch (err) {
      error(err.message || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.authContainer}>
      <div className={styles.authCard} style={{maxWidth: '600px'}}>
        <div className={styles.authHeader}>
          <h2>Create Account</h2>
          <p>Join us for all your puja samagri needs</p>
        </div>

        <form onSubmit={handleSubmit} className={styles.authForm}>
          <div className="grid grid-2 gap-4">
            <div className="form-group">
              <label className="form-label">First Name</label>
              <input type="text" className="form-input" required
                onChange={e => setFormData({...formData, first_name: e.target.value})} />
            </div>
            <div className="form-group">
              <label className="form-label">Last Name</label>
              <input type="text" className="form-input" required
                onChange={e => setFormData({...formData, last_name: e.target.value})} />
            </div>
          </div>

          <div className="grid grid-2 gap-4">
            <div className="form-group">
              <label className="form-label">Username *</label>
              <input type="text" className="form-input" required
                onChange={e => setFormData({...formData, username: e.target.value})} />
            </div>
            <div className="form-group">
              <label className="form-label">Email URL *</label>
              <input type="email" className="form-input" required
                onChange={e => setFormData({...formData, email: e.target.value})} />
            </div>
          </div>

          <div className="grid grid-2 gap-4">
            <div className="form-group">
              <label className="form-label">Phone</label>
              <input type="text" className="form-input"
                onChange={e => setFormData({...formData, phone: e.target.value})} />
            </div>
            <div className="form-group">
              <label className="form-label">City</label>
              <select className="form-select" onChange={e => setFormData({...formData, city: e.target.value})}>
                <option value="kathmandu">Kathmandu</option>
                <option value="lalitpur">Lalitpur</option>
                <option value="bhaktapur">Bhaktapur</option>
              </select>
            </div>
          </div>

          <div className="grid grid-2 gap-4">
            <div className="form-group">
              <label className="form-label">Password *</label>
              <input type="password" className="form-input" required minLength={6}
                onChange={e => setFormData({...formData, password: e.target.value})} />
            </div>
            <div className="form-group">
              <label className="form-label">Confirm Password *</label>
              <input type="password" className="form-input" required minLength={6}
                onChange={e => setFormData({...formData, password2: e.target.value})} />
            </div>
          </div>

          <button type="submit" className="btn btn-primary" style={{width: '100%', marginTop: '10px'}} disabled={loading}>
            {loading ? 'Registering...' : 'Register'}
          </button>
        </form>

        <div className={styles.authFooter}>
          <p>Already have an account? <Link href={`/auth/login?redirect=${redirect}`}>Login here</Link></p>
        </div>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="container section text-center">Loading...</div>}>
      <RegisterForm />
    </Suspense>
  );
}
