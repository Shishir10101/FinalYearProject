'use client';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { ordersAPI, productsAPI, authAPI } from '@/lib/api';
import Link from 'next/link';

export default function AccountPage() {
  const { user, updateProfile, logout } = useAuth();
  const router = useRouter();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ordersError, setOrdersError] = useState('');
  const [areas, setAreas] = useState([]);
  const [editing, setEditing] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    address: '',
    city: ''
  });

  // Security panel state. Kept separate from the profile form above: the two
  // write different endpoints and a failure in one must not clear the other.
  const [pwOpen, setPwOpen] = useState(false);
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', new_password2: '' });
  const [pwError, setPwError] = useState('');
  const [pwFieldErrors, setPwFieldErrors] = useState({});
  const [pwSaving, setPwSaving] = useState(false);
  const [signingOutAll, setSigningOutAll] = useState(false);
  const [securityNotice, setSecurityNotice] = useState(null);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    setOrdersError('');
    try {
      const data = await ordersAPI.list();
      setOrders(data.results || data);
    } catch (e) {
      // Previously this was swallowed by console.error, so a backend outage
      // rendered as "No orders yet." — the customer was told the wrong thing.
      setOrdersError(e.message || 'Could not load your orders.');
      setOrders([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) {
      setFormData({
        first_name: user.first_name || '',
        last_name: user.last_name || '',
        email: user.email || '',
        phone: user.profile?.phone || '',
        address: user.profile?.address || '',
        city: user.profile?.city || ''
      });
      fetchOrders();
    }
  }, [user, fetchOrders]);

  // Delivery areas come from the server so an area added in Catalog Settings
  // appears here without a code change. Previously this was three hardcoded
  // <option> tags.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await productsAPI.areas();
        if (!cancelled) setAreas(data.results || data || []);
      } catch {
        // Non-fatal: the profile form still works, the dropdown just falls back
        // to whatever the user already had saved.
        if (!cancelled) setAreas([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveError('');
    try {
      await updateProfile(formData);
      setEditing(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 4000);
    } catch (e) {
      setSaveError(e.message || 'Could not save your changes. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    setPwSaving(true);
    setPwError('');
    setPwFieldErrors({});
    try {
      await authAPI.changePassword(pwForm);
      // The server revoked **every** token for this account, including the one
      // this tab is holding. Continuing to browse would only produce 401s, so
      // the honest thing is to sign out locally and say why.
      logout();
      router.push('/auth/login?changed=1');
    } catch (err) {
      // The client attaches the raw DRF payload as `.fields` for exactly this
      // purpose. Rendering each message next to its own input is why this is a
      // form rather than a single flash message.
      const details = err?.fields;
      if (details && typeof details === 'object' && !Array.isArray(details)) {
        const flat = {};
        Object.entries(details).forEach(([field, msgs]) => {
          // Skip DRF's top-level `detail` key; it is a sentence, not a field.
          if (field === 'detail') return;
          flat[field] = Array.isArray(msgs) ? msgs.join(' ') : String(msgs);
        });
        if (Object.keys(flat).length > 0) {
          setPwFieldErrors(flat);
          setPwError('');
        } else {
          setPwError(err.message || 'Could not change your password. Please try again.');
        }
      } else {
        setPwError(err.message || 'Could not change your password. Please try again.');
      }
    } finally {
      setPwSaving(false);
    }
  };

  const handleLogoutAll = async () => {
    setSigningOutAll(true);
    setSecurityNotice(null);
    try {
      const res = await authAPI.logoutAll();
      // This session is revoked too, so the same reasoning as above applies.
      logout();
      router.push('/auth/login?signedout=all');
      return res;
    } catch (err) {
      setSecurityNotice({
        kind: 'error',
        text: err.message || 'Could not sign out other sessions. Please try again.',
      });
    } finally {
      setSigningOutAll(false);
    }
  };

  if (!user) return <div className="container section">Please login.</div>;

  // The saved city may be an area that no longer exists in the list; keep it as
  // an option so editing the profile does not silently reassign the customer.
  const cityOptions = [...areas];
  const knownSlug = cityOptions.some((a) => a.slug === formData.city);
  if (formData.city && !knownSlug) {
    cityOptions.push({ slug: formData.city, name: formData.city });
  }

  return (
    <div className="container section">
      <h1 className="section-title">My Account</h1>

      {saved && (
        <div className="notice notice-success" style={{ marginBottom: '20px' }}>
          Profile updated.
        </div>
      )}

      <div className="grid grid-2" style={{alignItems: 'start'}}>
        <div className="card p-4">
          <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '20px'}}>
             <h2>Profile Information</h2>
             {!editing && <button className="btn btn-outline btn-sm" onClick={() => setEditing(true)}>Edit</button>}
          </div>

          {editing ? (
            <form onSubmit={handleSubmit}>
               {saveError && <div className="notice notice-error" style={{marginBottom: '15px'}}>{saveError}</div>}
               <div className="grid grid-2 gap-3" style={{marginBottom:'15px'}}>
                  <div className="form-group mb-0">
                    <label className="form-label">First Name</label>
                    <input type="text" className="form-input" value={formData.first_name} onChange={e => setFormData({...formData, first_name: e.target.value})} />
                  </div>
                  <div className="form-group mb-0">
                    <label className="form-label">Last Name</label>
                    <input type="text" className="form-input" value={formData.last_name} onChange={e => setFormData({...formData, last_name: e.target.value})} />
                  </div>
               </div>
               <div className="form-group">
                 <label className="form-label">Email</label>
                 <input type="email" className="form-input" value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} />
               </div>
               <div className="grid grid-2 gap-3" style={{marginBottom:'15px'}}>
                  <div className="form-group mb-0">
                    <label className="form-label">Phone</label>
                    <input type="text" className="form-input" value={formData.phone} onChange={e => setFormData({...formData, phone: e.target.value})} />
                  </div>
                  <div className="form-group mb-0">
                    <label className="form-label">City</label>
                    <select className="form-select" value={formData.city} onChange={e => setFormData({...formData, city: e.target.value})}>
                      {cityOptions.length === 0 && <option value="">No areas available</option>}
                      {cityOptions.map((area) => (
                        <option key={area.slug} value={area.slug}>
                          {area.name.charAt(0).toUpperCase() + area.name.slice(1)}
                        </option>
                      ))}
                    </select>
                  </div>
               </div>
               <div className="form-group">
                 <label className="form-label">Address</label>
                 <textarea className="form-input" value={formData.address} onChange={e => setFormData({...formData, address: e.target.value})} rows="2"></textarea>
               </div>
               <div style={{display: 'flex', gap: '10px'}}>
                 <button type="submit" className="btn btn-primary" disabled={saving}>
                   {saving ? 'Saving…' : 'Save Changes'}
                 </button>
                 <button type="button" className="btn btn-outline" onClick={() => { setEditing(false); setSaveError(''); }} disabled={saving}>Cancel</button>
               </div>
            </form>
          ) : (
            <div style={{lineHeight: '1.8'}}>
               <p><strong>Name:</strong> {user.first_name} {user.last_name}</p>
               <p><strong>Username:</strong> {user.username}</p>
               <p><strong>Email:</strong> {user.email}</p>
               <p><strong>Phone:</strong> {user.profile?.phone || 'Not set'}</p>
               <p><strong>Address:</strong> {user.profile?.address || 'Not set'}</p>
               <p><strong>City:</strong> <span style={{textTransform:'capitalize'}}>{user.profile?.city || 'Not set'}</span></p>
            </div>
          )}
        </div>

        <div className="card p-4">
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '10px'}}>
            <h2>Recent Orders</h2>
            {orders.length > 0 && (
              <Link href="/account/orders" style={{fontSize: '0.9rem'}}>See all →</Link>
            )}
          </div>
          <div style={{marginTop: '20px'}}>
             {loading ? (
               <div style={{display: 'flex', flexDirection: 'column', gap: '15px'}}>
                 {[1, 2, 3].map(i => (
                   <div key={i} className="skeleton-block" style={{height: '110px', borderRadius: 'var(--radius-md)'}} />
                 ))}
               </div>
             ) : ordersError ? (
               <div className="empty-state">
                 <div className="empty-state-icon">⚠️</div>
                 <h3 className="empty-state-title">Could not load your orders</h3>
                 <p className="empty-state-text">{ordersError}</p>
                 <button className="btn btn-primary" style={{marginTop: '16px'}} onClick={fetchOrders}>
                   Try again
                 </button>
               </div>
             ) : orders.length === 0 ? (
               <div className="empty-state">
                 <div className="empty-state-icon">🛍️</div>
                 <h3 className="empty-state-title">No orders yet</h3>
                 <p className="empty-state-text">
                   When you place your first order it will appear here with live status tracking.
                 </p>
                 <Link href="/products" className="btn btn-primary" style={{marginTop: '16px', display: 'inline-block'}}>
                   Start shopping
                 </Link>
               </div>
             ) : (
              <div style={{display: 'flex', flexDirection: 'column', gap: '15px'}}>
                {orders.slice(0, 5).map(order => (
                  <div key={order.id} style={{padding: '15px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)'}}>
                     <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '8px', gap: '8px'}}>
                       <strong>Order #{order.id}</strong>
                       <span className={`badge ${order.status === 'delivered' ? 'badge-success' : order.status === 'cancelled' ? 'badge-danger' : 'badge-primary'}`}>
                         {order.status_display}
                       </span>
                     </div>
                     <p style={{fontSize: '0.9rem', color: 'var(--text-secondary)'}}>Date: {new Date(order.created_at).toLocaleDateString()}</p>
                     <p style={{fontSize: '0.9rem', color: 'var(--text-secondary)'}}>Total: Rs. {order.total_amount}</p>
                     <Link href={`/account/orders/${order.id}`} style={{display:'inline-block', marginTop: '10px', fontSize: '0.9rem'}}>View Details →</Link>
                  </div>
                ))}
              </div>
             )}
          </div>
        </div>
      </div>

      {/*
        Security. Neither control had a home before: `/auth/password-change/` did
        not exist at all, and `/auth/logout-all/` had existed since Day 7 with the
        API docs describing it as "a real user-facing action" and no client calling
        it. Both sit together because they answer the same question — what do I do
        if someone else may have access to my account.
      */}
      <div className="card p-4" style={{ marginTop: '20px' }} data-testid="account-security">
        <h2>Account Security</h2>
        <p className="field-hint" style={{ marginTop: '6px', marginBottom: '20px' }}>
          Your password is the only way into this account. Changing it signs out every
          device, including this one.
        </p>

        {securityNotice && (
          <div
            className={`notice ${securityNotice.kind === 'error' ? 'notice-error' : 'notice-success'}`}
            role={securityNotice.kind === 'error' ? 'alert' : 'status'}
            style={{ marginBottom: '16px' }}
          >
            {securityNotice.text}
          </div>
        )}

        {!pwOpen ? (
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-outline"
              data-testid="open-change-password"
              onClick={() => { setPwOpen(true); setPwError(''); setPwFieldErrors({}); }}
            >
              Change password
            </button>
            <button
              type="button"
              className="btn btn-outline"
              data-testid="sign-out-everywhere"
              disabled={signingOutAll}
              onClick={handleLogoutAll}
            >
              {signingOutAll ? 'Signing out…' : 'Sign out everywhere'}
            </button>
          </div>
        ) : (
          <form onSubmit={handlePasswordChange} style={{ maxWidth: '440px' }}>
            {pwError && (
              <div className="notice notice-error" role="alert" style={{ marginBottom: '15px' }}>
                {pwError}
              </div>
            )}

            <div className="form-group">
              <label className="form-label" htmlFor="current-password">Current password</label>
              <input
                id="current-password"
                type="password"
                className="form-input"
                autoComplete="current-password"
                value={pwForm.current_password}
                onChange={(e) => setPwForm({ ...pwForm, current_password: e.target.value })}
              />
              {pwFieldErrors.current_password && (
                <p className="field-error" style={{ color: '#c62828', fontSize: '0.85rem', marginTop: '4px' }}>
                  {pwFieldErrors.current_password}
                </p>
              )}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="new-password-1">New password</label>
              <input
                id="new-password-1"
                type="password"
                className="form-input"
                autoComplete="new-password"
                value={pwForm.new_password}
                onChange={(e) => setPwForm({ ...pwForm, new_password: e.target.value })}
              />
              {pwFieldErrors.new_password && (
                <p className="field-error" style={{ color: '#c62828', fontSize: '0.85rem', marginTop: '4px' }}>
                  {pwFieldErrors.new_password}
                </p>
              )}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="new-password-2">Confirm new password</label>
              <input
                id="new-password-2"
                type="password"
                className="form-input"
                autoComplete="new-password"
                value={pwForm.new_password2}
                onChange={(e) => setPwForm({ ...pwForm, new_password2: e.target.value })}
              />
              {pwFieldErrors.new_password2 && (
                <p className="field-error" style={{ color: '#c62828', fontSize: '0.85rem', marginTop: '4px' }}>
                  {pwFieldErrors.new_password2}
                </p>
              )}
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                type="submit"
                className="btn btn-primary"
                data-testid="submit-change-password"
                disabled={pwSaving}
              >
                {pwSaving ? 'Changing…' : 'Change password'}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                disabled={pwSaving}
                onClick={() => {
                  setPwOpen(false);
                  setPwError('');
                  setPwFieldErrors({});
                  setPwForm({ current_password: '', new_password: '', new_password2: '' });
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
