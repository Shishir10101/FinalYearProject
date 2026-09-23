'use client';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { api, fieldErrors } from '@/lib/api';
import { useAdmin } from '@/context/AdminContext';
import Modal from '@/components/Modal';
import ConfirmDialog from '@/components/ConfirmDialog';
import ImageField from '@/components/ImageField';

const EMPTY_FORM = {
  name: '',
  description: '',
  price: '',
  stock: '',
  category: '',
  vendor: '',
  unit: 'piece',
  is_featured: false,
  is_active: true,
};

/** Fields that render their own inline error next to the input. */
const INLINE_ERROR_FIELDS = ['name', 'description', 'price', 'stock', 'category', 'vendor', 'image'];

export default function ProductsPage() {
  const { isManager } = useAdmin();
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState(null);

  // dialog state: null | 'create' | product object
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState({});
  const [form, setForm] = useState(EMPTY_FORM);
  // Three-valued on purpose:
  //   `undefined` — the image was not touched, send JSON as before
  //   a `File`    — a new image was picked, send multipart
  //   `null`      — the existing image was removed, send `image: null`
  // Collapsing `undefined` and `null` would make "leave it alone" and "delete it"
  // the same instruction, and every edit would wipe the picture.
  const [imageFile, setImageFile] = useState(undefined);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [p, c, v] = await Promise.all([
        api.get('/products/admin/products/'),
        api.get('/products/admin/categories/'),
        api.get('/products/admin/vendors/'),
      ]);
      setProducts(p.results || p || []);
      setCategories(c.results || c || []);
      setVendors(v.results || v || []);
    } catch (e) {
      setError(e.message || 'Failed to load products.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const flash = (text, kind = 'success') => {
    setNotice({ text, kind });
    setTimeout(() => setNotice(null), 4000);
  };

  const openCreate = () => {
    setForm({
      ...EMPTY_FORM,
      category: categories[0]?.id ?? '',
      // A vendor's new products are always attributed to them server-side
      // (`AdminProductListCreateView.perform_create`), and `/admin/vendors/` is
      // scoped to their own record — so prefill it. Leaving it blank made the
      // read-only field below fall through to its "Your shop" placeholder instead
      // of naming the shop, which is a label that does not say the true thing.
      vendor: isManager ? '' : (vendors[0]?.id ?? ''),
    });
    setFormError({});
    setImageFile(undefined);
    setEditing('create');
  };

  const openEdit = (product) => {
    setForm({
      name: product.name ?? '',
      description: product.description ?? '',
      price: product.price ?? '',
      stock: product.stock ?? 0,
      category: product.category ?? '',
      vendor: product.vendor ?? '',
      unit: product.unit ?? 'piece',
      is_featured: !!product.is_featured,
      is_active: product.is_active !== false,
    });
    setFormError({});
    setImageFile(undefined);
    setEditing(product);
  };

  /**
   * Turn the form payload into multipart parts.
   *
   * `null` becomes `''` — DRF reads an empty string as "clear this FK" for a
   * nullable relation, whereas the literal string `"null"` would be rejected as an
   * invalid pk. Booleans must be sent as `'true'`/`'false'`: `String(false)` is
   * `"false"` which is fine, but `String(0)` and an empty part are not the same
   * thing, so the boolean case is handled explicitly.
   */
  const toFormData = (payload, file) => {
    const fd = new FormData();
    Object.entries(payload).forEach(([key, value]) => {
      if (value === null || value === undefined) fd.append(key, '');
      else if (typeof value === 'boolean') fd.append(key, value ? 'true' : 'false');
      else fd.append(key, String(value));
    });
    fd.append('image', file);
    return fd;
  };

  const submit = async () => {
    setBusy(true);
    setFormError({});
    // Empty strings must become null for the FK fields, not "".
    const payload = {
      ...form,
      category: form.category === '' ? null : Number(form.category),
      vendor: form.vendor === '' ? null : Number(form.vendor),
      price: form.price === '' ? '0' : String(form.price),
      stock: form.stock === '' ? 0 : Number(form.stock),
    };
    const isCreate = editing === 'create';
    try {
      if (imageFile instanceof File) {
        // A new picture: multipart, because a JSON body cannot carry a file.
        await api.upload(
          isCreate ? '/products/admin/products/' : `/products/admin/products/${editing.id}/`,
          toFormData(payload, imageFile),
          isCreate ? 'POST' : 'PATCH',
        );
      } else if (imageFile === null && !isCreate) {
        // Removal. A multipart body cannot express "no file" — an empty part is
        // rejected as not-a-file — so this goes as JSON `null`, which the model's
        // `null=True` makes `allow_null` and which clears the column.
        await api.patch(`/products/admin/products/${editing.id}/`, { ...payload, image: null });
      } else if (isCreate) {
        await api.post('/products/admin/products/', payload);
      } else {
        await api.patch(`/products/admin/products/${editing.id}/`, payload);
      }

      flash(isCreate ? 'Product created.' : 'Product updated.');
      setEditing(null);
      setImageFile(undefined);
      await fetchAll();
    } catch (e) {
      // The API client keeps the parsed DRF body on `e.body`, so the per-field
      // spans below can be populated instead of dumping one banner. Previously
      // this always set `_general`, which meant the per-field markup was dead
      // code and a bad price highlighted nothing.
      setFormError(fieldErrors(e.body, e.message || 'Could not save the product.'));
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    setBusy(true);
    try {
      await api.delete(`/products/admin/products/${deleting.id}/`);
      flash(`“${deleting.name}” deleted.`);
      setDeleting(null);
      await fetchAll();
    } catch (e) {
      flash(e.message || 'Could not delete the product.', 'error');
      setDeleting(null);
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (product) => {
    // Optimistic: flip locally, reconcile on failure.
    setProducts((prev) =>
      prev.map((p) => (p.id === product.id ? { ...p, is_active: !p.is_active } : p))
    );
    try {
      await api.patch(`/products/admin/products/${product.id}/`, {
        is_active: !product.is_active,
      });
      flash(`“${product.name}” ${product.is_active ? 'deactivated' : 'activated'}.`);
    } catch (e) {
      setProducts((prev) =>
        prev.map((p) => (p.id === product.id ? { ...p, is_active: product.is_active } : p))
      );
      flash(e.message || 'Could not update the product.', 'error');
    }
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return products;
    return products.filter(
      (p) =>
        p.name?.toLowerCase().includes(q) ||
        (p.category_name || '').toLowerCase().includes(q) ||
        (p.vendor_name || '').toLowerCase().includes(q)
    );
  }, [products, search]);

  const getStockBadge = (stock) => {
    if (stock === 0) return <span className="badge badge-danger">Out of Stock</span>;
    if (stock < 10) return <span className="badge badge-warning">Low ({stock})</span>;
    return <span className="badge badge-success">Good ({stock})</span>;
  };

  return (
    <div>
      <div className="header">
        <h1>Product Inventory</h1>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-outline" onClick={fetchAll} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          <button
            className="btn btn-primary"
            onClick={openCreate}
            disabled={loading || !!error || categories.length === 0}
            title={categories.length === 0 ? 'Create a category first' : undefined}
          >
            + New Product
          </button>
        </div>
      </div>

      {notice && (
        <div
          className={`notice ${notice.kind === 'error' ? 'notice-error' : 'notice-success'}`}
          role={notice.kind === 'error' ? 'alert' : 'status'}
          aria-live={notice.kind === 'error' ? 'assertive' : 'polite'}
        >
          {notice.text}
        </div>
      )}

      {!loading && !error && (
        <>
          <div className="grid grid-4" style={{ marginBottom: '30px' }}>
            <div className="card stat-card">
              <span className="stat-label">Total Products</span>
              <span className="stat-value">{products.length}</span>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Out of Stock</span>
              <span className="stat-value" style={{ color: '#c62828' }}>
                {products.filter((p) => p.stock === 0).length}
              </span>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Low Stock</span>
              <span className="stat-value" style={{ color: '#e65100' }}>
                {products.filter((p) => p.stock > 0 && p.stock < 10).length}
              </span>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Inactive</span>
              <span className="stat-value">{products.filter((p) => !p.is_active).length}</span>
            </div>
          </div>

          <div style={{ marginBottom: '16px' }}>
            <input
              type="text"
              className="search-input"
              placeholder="Search by name, category, or vendor…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search products"
            />
          </div>
        </>
      )}

      <div className="card">
        {loading ? (
          <div>
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="skeleton-line" style={{ height: '38px' }} />
            ))}
          </div>
        ) : error ? (
          <div className="state-block state-error">
            <span className="state-icon">⚠️</span>
            <h3>Could not load products</h3>
            <p>{error}</p>
            <button className="btn btn-primary" style={{ marginTop: '16px' }} onClick={fetchAll}>
              Try again
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="state-inline">
            {search
              ? `No products match “${search}”.`
              : 'No products in the catalog yet. Use “New Product” to add the first one.'}
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Category</th>
                <th>Vendor</th>
                <th>Price</th>
                <th>Stock</th>
                <th>Active</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((product) => (
                <tr key={product.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {/* A thumbnail, because "does this product have a picture?" is
                          the question this column now exists to answer — and until
                          the upload widget was added there was no way to tell without
                          opening every product in turn. */}
                      <span
                        style={{
                          width: '34px', height: '34px', flex: '0 0 auto',
                          borderRadius: 'var(--radius-sm)', overflow: 'hidden',
                          background: 'var(--bg-secondary)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}
                      >
                        {product.image ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={product.image}
                            alt=""
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          />
                        ) : (
                          <span style={{ fontSize: '0.9rem', opacity: 0.4 }} aria-hidden="true">🪔</span>
                        )}
                      </span>
                      <span>
                        <strong>{product.name}</strong>
                        {product.is_featured && (
                          <span className="badge badge-neutral" style={{ marginLeft: '6px' }}>
                            Featured
                          </span>
                        )}
                        <div className="field-hint">per {product.unit || 'piece'}</div>
                      </span>
                    </div>
                  </td>
                  <td>{product.category_name || '—'}</td>
                  <td>{product.vendor_name || <span className="field-hint">Unassigned</span>}</td>
                  <td>Rs. {product.price}</td>
                  <td>{getStockBadge(product.stock)}</td>
                  <td>
                    <span className={`badge ${product.is_active ? 'badge-success' : 'badge-danger'}`}>
                      {product.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button className="btn btn-ghost btn-sm" onClick={() => openEdit(product)}>
                        Edit
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={() => toggleActive(product)}>
                        {product.is_active ? 'Disable' : 'Enable'}
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={() => setDeleting(product)}>
                        Delete
                      </button>
          </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
      </div>

      {editing && (
        <Modal
          title={editing === 'create' ? 'New Product' : `Edit “${editing.name}”`}
          onClose={busy ? () => {} : () => setEditing(null)}
          wide
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => setEditing(null)} disabled={busy}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={submit} disabled={busy}>
                {busy ? 'Saving…' : editing === 'create' ? 'Create Product' : 'Save Changes'}
              </button>
            </>
          }
        >
          {formError._general && (
            <div className="notice notice-error">{formError._general}</div>
          )}

          <div className="field">
            <label htmlFor="p-name">Name</label>
            <input
              id="p-name"
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Pashupatinath Puja Thali"
            />
            {formError.name && <span className="field-error">{formError.name}</span>}
          </div>

          <div className="field">
            <label htmlFor="p-desc">Description</label>
            <textarea
              id="p-desc"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="What is included, and what it is used for."
            />
            {formError.description && <span className="field-error">{formError.description}</span>}
          </div>

          <div className="form-row">
            <div className="field">
              <label htmlFor="p-price">Price (NPR)</label>
              <input
                id="p-price"
                type="number"
                min="0"
                step="0.01"
                value={form.price}
                onChange={(e) => setForm({ ...form, price: e.target.value })}
              />
              {formError.price && <span className="field-error">{formError.price}</span>}
            </div>
            <div className="field">
              <label htmlFor="p-stock">Stock (units)</label>
              <input
                id="p-stock"
                type="number"
                min="0"
                step="1"
                value={form.stock}
                onChange={(e) => setForm({ ...form, stock: e.target.value })}
              />
              {formError.stock && <span className="field-error">{formError.stock}</span>}
            </div>
          </div>

          <div className="form-row">
            <div className="field">
              <label htmlFor="p-category">Category</label>
              <select
                id="p-category"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              >
                <option value="">— Select —</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              {formError.category && <span className="field-error">{formError.category}</span>}
            </div>
            <div className="field">
              <label htmlFor="p-vendor">Vendor</label>
              {isManager ? (
                <select
                  id="p-vendor"
                  value={form.vendor}
                  onChange={(e) => setForm({ ...form, vendor: e.target.value })}
                >
                  <option value="">— Unassigned —</option>
                  {vendors.map((v) => (
                    <option key={v.id} value={v.id}>{v.shop_name}</option>
                  ))}
                </select>
              ) : (
                // A vendor cannot assign ownership; the server forces their own
                // row regardless of what is sent. Showing the picker would imply
                // a choice they do not have.
                <input
                  id="p-vendor"
                  type="text"
                  value={vendors.find((v) => String(v.id) === String(form.vendor))?.shop_name || 'Your shop'}
                  readOnly
                  disabled
                />
              )}
              {formError.vendor && <span className="field-error">{formError.vendor}</span>}
            </div>
          </div>

          <div className="field">
            <label htmlFor="p-unit">Unit</label>
            <input
              id="p-unit"
              type="text"
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
              placeholder="piece, packet, kg, bundle"
            />
            <span className="field-hint">Shown next to the price on the storefront.</span>
          </div>

          <ImageField
            currentUrl={editing !== 'create' ? editing.image : null}
            onSelect={setImageFile}
            disabled={busy}
            error={formError.image}
            hint={
              editing !== 'create' && !editing.image
                ? 'No image yet — the storefront shows a placeholder lamp until you add one.'
                : undefined
            }
          />

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.is_featured}
              onChange={(e) => setForm({ ...form, is_featured: e.target.checked })}
            />
            Feature on the home page
          </label>

          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            Visible in the storefront
          </label>

          {/*
            Safety net. Every field above renders its own error, but the server
            can reject something with no input here (an image, a slug, a field
            added later). Without this, such a response would leave the dialog
            open with no visible reason — the exact silent failure this pass is
            meant to eliminate.
          */}
          {Object.entries(formError)
            .filter(([key]) => key !== '_general' && !INLINE_ERROR_FIELDS.includes(key))
            .map(([key, message]) => (
              <span key={key} className="field-error">{key}: {message}</span>
            ))}
        </Modal>
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete this product?"
          body={
            <>
              <strong>{deleting.name}</strong> will be permanently removed from the
              catalog. This cannot be undone. If you only want to hide it from the
              storefront, use <strong>Disable</strong> instead.
            </>
          }
          busy={busy}
          onConfirm={confirmDelete}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
