'use client';
import { useState, useEffect, useCallback } from 'react';
import { api, fieldErrors } from '@/lib/api';
import { useAdmin } from '@/context/AdminContext';
import Modal from '@/components/Modal';
import ConfirmDialog from '@/components/ConfirmDialog';

/**
 * Taxonomy and delivery-area management.
 *
 * These two belong on one screen because they are the same kind of thing: small
 * lookup tables an admin edits rarely and needs to see in full. Areas replaced
 * the old hardcoded CITY_CHOICES enum, so this page is what makes
 * "area management" real rather than aspirational.
 *
 * Managers only. A vendor reaching this route directly (by typing the URL) gets
 * an explanatory panel rather than a broken-looking empty table — and every
 * write here would be rejected with a 403 anyway, because the server checks the
 * role rather than trusting the navigation that got you here.
 */
export default function SettingsPage() {
  const { isManager, loading: authLoading } = useAdmin();
  const [tab, setTab] = useState('categories');

  if (authLoading) {
    return <div className="state-inline" style={{ marginTop: '40px' }}>Checking your session…</div>;
  }

  if (!isManager) {
    return (
      <div>
        <div className="header">
          <h1>Catalog Settings</h1>
        </div>
        <div className="card">
          <div className="state-block">
            <span className="state-icon">🔒</span>
            <h3>Not available for your role</h3>
            <p>
              Categories and delivery areas are managed by an administrator. You can
              still manage your own products from the Products page.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="header">
        <h1>Catalog Settings</h1>
      </div>
      <div className="tabs">
        <button
          className={`tab ${tab === 'categories' ? 'tab-active' : ''}`}
          onClick={() => setTab('categories')}
        >
          Categories
        </button>
        <button
          className={`tab ${tab === 'areas' ? 'tab-active' : ''}`}
          onClick={() => setTab('areas')}
        >
          Delivery Areas
        </button>
      </div>
      {tab === 'categories' ? <CategoriesPanel /> : <AreasPanel />}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function useCrud(endpoint, label) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [formError, setFormError] = useState('');
  const [fieldError, setFieldError] = useState({});
  const [form, setForm] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.get(endpoint);
      setRows(data.results || data || []);
    } catch (e) {
      setError(e.message || `Could not load ${label}.`);
    } finally {
      setLoading(false);
    }
  }, [endpoint, label]);

  useEffect(() => { load(); }, [load]);

  const flash = (text, kind = 'success') => {
    setNotice({ text, kind });
    setTimeout(() => setNotice(null), 4000);
  };

  /**
   * `override` lets a caller normalise the payload without waiting for setState.
   *
   * It must be a **plain object**, and that is enforced rather than assumed.
   * `onClick={save}` instead of `onClick={() => save()}` hands this a React event as the
   * first argument, which then *became the payload*: `JSON.stringify` on a synthetic
   * event throws on its circular structure, so the request never fired and the dialog sat
   * open. **Creating a category from this screen was simply broken** — the Areas tab
   * happened to call a local wrapper that builds its payload explicitly, so only one of
   * the two panels was affected and the dashboard looked fine.
   *
   * A synthetic event always carries `nativeEvent`, which a payload never does.
   */
  const save = async (override) => {
    const isOverride = override !== null
      && typeof override === 'object'
      && !('nativeEvent' in override);
    const payload = isOverride ? override : form;
    setBusy(true);
    setFormError('');
    setFieldError({});
    try {
      if (editing?.id) {
        await api.patch(`${endpoint}${editing.id}/`, payload);
        flash(`${label.replace(/s$/, '')} updated.`);
      } else {
        await api.post(endpoint, payload);
        flash(`${label.replace(/s$/, '')} created.`);
      }
      setEditing(null);
      await load();
    } catch (e) {
      // Per-field messages mark the offending input. The fallback only lands in
      // `_general` when nothing could be attributed to a field, so a 400 with
      // field detail does not also produce a redundant banner.
      const perField = fieldErrors(e.body, e.message || 'Could not save.');
      setFieldError(perField);
      setFormError(perField._general || '');
    } finally {
      setBusy(false);
    }
  };

  const destroy = async () => {
    setBusy(true);
    try {
      await api.delete(`${endpoint}${deleting.id}/`);
      flash(`Deleted.`);
      setDeleting(null);
      await load();
    } catch (e) {
      // A 409-style refusal (row still referenced) must read as an explanation,
      // not as a silent failure.
      flash(e.message || 'Could not delete — it may still be in use.', 'error');
      setDeleting(null);
    } finally {
      setBusy(false);
    }
  };

  return {
    rows, loading, error, notice, busy, editing, deleting, formError, form,
    fieldError, setFieldError,
    setEditing, setDeleting, setFormError, setForm, save, destroy, load, flash,
  };
}

/* ------------------------------------------------------------------ */

function CategoriesPanel() {
  const c = useCrud('/products/admin/categories/', 'categories');

  const openCreate = () => {
    c.setForm({ name: '', description: '' });
    c.setFormError('');
    c.setFieldError({});
    c.setEditing('create');
  };
  const openEdit = (row) => {
    c.setForm({ name: row.name, description: row.description || '' });
    c.setFormError('');
    c.setFieldError({});
    c.setEditing(row);
  };

  return (
    <div className="card">
      <div className="header" style={{ marginBottom: '18px' }}>
        <h2 style={{ fontSize: '1rem', margin: 0 }}>Categories</h2>
        <button className="btn btn-primary" onClick={openCreate}>+ New Category</button>
      </div>

      {c.notice && (
        <div
          className={`notice ${c.notice.kind === 'error' ? 'notice-error' : 'notice-success'}`}
          role={c.notice.kind === 'error' ? 'alert' : 'status'}
          aria-live={c.notice.kind === 'error' ? 'assertive' : 'polite'}
        >
          {c.notice.text}
        </div>
      )}

      {c.loading ? (
        [1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ height: '34px' }} />)
      ) : c.error ? (
        <div className="state-block state-error">
          <span className="state-icon">⚠️</span>
          <h3>Could not load categories</h3>
          <p>{c.error}</p>
          <button className="btn btn-primary" style={{ marginTop: '16px' }} onClick={c.load}>
            Try again
          </button>
        </div>
      ) : c.rows.length === 0 ? (
        <div className="state-inline">No categories yet. Create one to start listing products.</div>
      ) : (
        <div className="table-wrap">
          <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Slug</th>
              <th>Description</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {c.rows.map((row) => (
              <tr key={row.id}>
                <td><strong>{row.name}</strong></td>
                <td><code className="field-hint">{row.slug}</code></td>
                <td className="field-hint">{row.description || '—'}</td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => openEdit(row)}>Edit</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => c.setDeleting(row)}>Delete</button>
        </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      {c.editing && (
        <Modal
          title={c.editing === 'create' ? 'New Category' : `Edit “${c.editing.name}”`}
          onClose={c.busy ? () => {} : () => c.setEditing(null)}
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => c.setEditing(null)} disabled={c.busy}>
                Cancel
              </button>
              {/* `() => c.save()` — not `c.save`. Handing the click event straight to a
                  handler that takes a payload argument is what broke this button; see the
                  guard on `save` above. */}
              <button className="btn btn-primary" onClick={() => c.save()} disabled={c.busy}>
                {c.busy ? 'Saving…' : 'Save'}
              </button>
            </>
          }
        >
          {c.formError && <div className="notice notice-error">{c.formError}</div>}
          <div className="field">
            <label htmlFor="c-name">Name</label>
            <input
              id="c-name" type="text" value={c.form.name || ''}
              className={c.fieldError.name ? 'input-invalid' : ''}
              aria-invalid={c.fieldError.name ? 'true' : undefined}
              aria-describedby={c.fieldError.name ? 'c-name-error' : undefined}
              onChange={(e) => c.setForm({ ...c.form, name: e.target.value })}
              placeholder="e.g. Puja Oils & Ghee"
            />
            {c.fieldError.name
              ? <span className="field-error" id="c-name-error">{c.fieldError.name}</span>
              : <span className="field-hint">The slug is generated automatically.</span>}
          </div>
          <div className="field">
            <label htmlFor="c-desc">Description</label>
            <textarea
              id="c-desc" value={c.form.description || ''}
              onChange={(e) => c.setForm({ ...c.form, description: e.target.value })}
            />
          </div>
          {/* Safety net: any field the server rejects that has no input above
              still gets shown, instead of vanishing into a silent failure. */}
          {Object.entries(c.fieldError)
            .filter(([key]) => key !== '_general' && key !== 'name')
            .map(([key, message]) => (
              <span key={key} className="field-error">{key}: {message}</span>
            ))}
        </Modal>
      )}

      {c.deleting && (
        <ConfirmDialog
          title="Delete this category?"
          body={
            <>
              <strong>{c.deleting.name}</strong> will be removed. Products still assigned to it may
              be affected — reassign them first if you are unsure.
            </>
          }
          busy={c.busy}
          onConfirm={c.destroy}
          onCancel={() => c.setDeleting(null)}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function AreasPanel() {
  const c = useCrud('/products/admin/areas/', 'areas');

  const openCreate = () => {
    c.setForm({ name: '', district: '', delivery_fee: '', is_active: true });
    c.setFormError('');
    c.setFieldError({});
    c.setEditing('create');
  };
  const openEdit = (row) => {
    c.setForm({
      name: row.name,
      district: row.district || '',
      delivery_fee: row.delivery_fee ?? '',
      is_active: row.is_active !== false,
    });
    c.setFormError('');
    c.setFieldError({});
    c.setEditing(row);
  };

  const save = () => {
    // `delivery_fee` arrives from the number input as a string; DRF wants null
    // (not "") to mean "use the default fee". Passed as an override because
    // setState has not flushed by the time save() reads `form`.
    c.save({
      ...c.form,
      delivery_fee: c.form.delivery_fee === '' ? null : String(c.form.delivery_fee),
    });
  };

  return (
    <div className="card">
      <div className="header" style={{ marginBottom: '18px' }}>
        <h2 style={{ fontSize: '1rem', margin: 0 }}>Delivery Areas</h2>
        <button className="btn btn-primary" onClick={openCreate}>+ New Area</button>
      </div>

      <p className="field-hint" style={{ marginTop: 0 }}>
        Areas available at checkout. Each may override the store-wide delivery fee;
        leave it blank to use the default.
      </p>

      {c.notice && (
        <div
          className={`notice ${c.notice.kind === 'error' ? 'notice-error' : 'notice-success'}`}
          role={c.notice.kind === 'error' ? 'alert' : 'status'}
          aria-live={c.notice.kind === 'error' ? 'assertive' : 'polite'}
        >
          {c.notice.text}
        </div>
      )}

      {c.loading ? (
        [1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ height: '34px' }} />)
      ) : c.error ? (
        <div className="state-block state-error">
          <span className="state-icon">⚠️</span>
          <h3>Could not load areas</h3>
          <p>{c.error}</p>
          <button className="btn btn-primary" style={{ marginTop: '16px' }} onClick={c.load}>
            Try again
          </button>
        </div>
      ) : c.rows.length === 0 ? (
        <div className="state-inline">No delivery areas configured. Checkout will have no options.</div>
      ) : (
        <div className="table-wrap">
          <table className="table">
          <thead>
            <tr>
              <th>Area</th>
              <th>District</th>
              <th>Delivery Fee</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {c.rows.map((row) => (
              <tr key={row.id}>
                <td><strong>{row.name}</strong></td>
                <td>{row.district || '—'}</td>
                <td>
                  {row.delivery_fee
                    ? `Rs. ${row.delivery_fee}`
                    : <span className="field-hint">Default</span>}
                </td>
                <td>
                  <span className={`badge ${row.is_active ? 'badge-success' : 'badge-danger'}`}>
                    {row.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => openEdit(row)}>Edit</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => c.setDeleting(row)}>Delete</button>
        </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      {c.editing && (
        <Modal
          title={c.editing === 'create' ? 'New Delivery Area' : `Edit “${c.editing.name}”`}
          onClose={c.busy ? () => {} : () => c.setEditing(null)}
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => c.setEditing(null)} disabled={c.busy}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={save} disabled={c.busy}>
                {c.busy ? 'Saving…' : 'Save'}
              </button>
            </>
          }
        >
          {c.formError && <div className="notice notice-error">{c.formError}</div>}
          <div className="form-row">
            <div className="field">
              <label htmlFor="a-name">Area Name</label>
              <input
                id="a-name" type="text" value={c.form.name || ''}
                className={c.fieldError.name ? 'input-invalid' : ''}
                aria-invalid={c.fieldError.name ? 'true' : undefined}
                aria-describedby={c.fieldError.name ? 'a-name-error' : undefined}
                onChange={(e) => c.setForm({ ...c.form, name: e.target.value })}
                placeholder="e.g. Bhaktapur"
              />
              {c.fieldError.name && (
                <span className="field-error" id="a-name-error">{c.fieldError.name}</span>
              )}
            </div>
            <div className="field">
              <label htmlFor="a-district">District</label>
              <input
                id="a-district" type="text" value={c.form.district || ''}
                onChange={(e) => c.setForm({ ...c.form, district: e.target.value })}
                placeholder="e.g. Bhaktapur"
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="a-fee">Delivery Fee Override (NPR)</label>
            <input
              id="a-fee" type="number" min="0" step="0.01" value={c.form.delivery_fee ?? ''}
              className={c.fieldError.delivery_fee ? 'input-invalid' : ''}
              aria-invalid={c.fieldError.delivery_fee ? 'true' : undefined}
              aria-describedby={c.fieldError.delivery_fee ? 'a-fee-error' : undefined}
              onChange={(e) => c.setForm({ ...c.form, delivery_fee: e.target.value })}
            />
            {c.fieldError.delivery_fee
              ? <span className="field-error" id="a-fee-error">{c.fieldError.delivery_fee}</span>
              : <span className="field-hint">Leave blank to use the store-wide default fee.</span>}
          </div>
          <label className="checkbox-field">
            <input
              type="checkbox" checked={c.form.is_active !== false}
              onChange={(e) => c.setForm({ ...c.form, is_active: e.target.checked })}
            />
            Available at checkout
          </label>
          {/* Safety net — see the note on the category modal above. */}
          {Object.entries(c.fieldError)
            .filter(([key]) => key !== '_general' && !['name', 'delivery_fee'].includes(key))
            .map(([key, message]) => (
              <span key={key} className="field-error">{key}: {message}</span>
            ))}
        </Modal>
      )}

      {c.deleting && (
        <ConfirmDialog
          title="Delete this area?"
          body={
            <>
              <strong>{c.deleting.name}</strong> will no longer be selectable at checkout. Existing
              orders keep their recorded city.
            </>
          }
          busy={c.busy}
          onConfirm={c.destroy}
          onCancel={() => c.setDeleting(null)}
        />
      )}
    </div>
  );
}
