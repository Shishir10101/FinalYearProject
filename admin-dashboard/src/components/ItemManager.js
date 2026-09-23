'use client';
import { useState, useEffect } from 'react';
import { api, fieldErrors } from '@/lib/api';
import styles from './ItemManager.module.css';

/**
 * The item list of a kit or a ritual.
 *
 * Both are the same shape — a parent, plus rows of (product, quantity,
 * is_required) — and both backends expose the same endpoints under different
 * paths, so one component drives both. Writing it twice is how the three product
 * cards drifted apart before they were merged into `ProductCard`.
 *
 * @param {'kit'|'puja'} parentType  Used for copy and as the payload key the
 *                                   serializer expects.
 * @param {number} parentId
 * @param {string} itemsUrl          List + create.
 * @param {function} itemUrl         (id) => detail url, for edit and delete.
 * @param {Array}  items             Current rows, already fetched by the parent.
 * @param {function} onChanged       Refetch the parent after any write.
 * @param {boolean} canEdit          Vendors may read a kit but not change it.
 */
export default function ItemManager({
  parentType, parentId, itemsUrl, itemUrl, items, onChanged, canEdit,
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [notice, setNotice] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const noun = parentType === 'kit' ? 'kit' : 'ritual';

  // --- product search -------------------------------------------------
  useEffect(() => {
    if (!canEdit) return undefined;
    const term = query.trim();
    if (term.length < 2) {
      setResults([]);
      return undefined;
    }

    let cancelled = false;
    // Debounced: typing "dhoop" should not fire five requests.
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await api.get(
          `/products/admin/products/?search=${encodeURIComponent(term)}`
        );
        if (!cancelled) setResults(Array.isArray(data) ? data : (data.results || []));
      } catch (e) {
        if (!cancelled) setNotice({ kind: 'error', text: e.message || 'Search failed.' });
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 300);

    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, canEdit]);

  const alreadyIn = (productId) => items.some((item) => item.product === productId);

  // --- writes ---------------------------------------------------------
  const addItem = async (product) => {
    setBusyId(product.id);
    setNotice(null);
    try {
      await api.post(itemsUrl, {
        [parentType]: parentId,
        product: product.id,
        quantity: 1,
        is_required: true,
      });
      setQuery('');
      setResults([]);
      await onChanged();
      setNotice({ kind: 'success', text: `Added ${product.name}.` });
    } catch (e) {
      // `fieldErrors` folds DRF's `non_field_errors` into `_general`, which is
      // where the (parent, product) uniqueness violation lands.
      const errs = fieldErrors(e.body, e.message || 'Could not add that product.');
      setNotice({
        kind: 'error',
        text: errs._general || errs.product || `Could not add ${product.name}.`,
      });
    } finally {
      setBusyId(null);
    }
  };

  const patchItem = async (item, changes) => {
    setBusyId(item.id);
    setNotice(null);
    try {
      await api.patch(itemUrl(item.id), changes);
      await onChanged();
    } catch (e) {
      const errs = fieldErrors(e.body, e.message || 'Could not update that item.');
      setNotice({ kind: 'error', text: errs._general || errs.quantity || 'Could not update.' });
    } finally {
      setBusyId(null);
    }
  };

  const removeItem = async (item) => {
    setBusyId(item.id);
    setNotice(null);
    try {
      await api.delete(itemUrl(item.id));
      await onChanged();
      setNotice({ kind: 'success', text: `Removed ${item.product_name}.` });
    } catch (e) {
      setNotice({ kind: 'error', text: e.message || 'Could not remove that item.' });
    } finally {
      setBusyId(null);
    }
  };

  const requiredCount = items.filter((i) => i.is_required).length;

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <div>
          <h3 className={styles.title}>Items</h3>
          <p className={styles.summary}>
            {items.length} item{items.length === 1 ? '' : 's'} · {requiredCount} required
          </p>
        </div>
      </div>

      {notice && (
        <div
          className={`notice notice-${notice.kind === 'error' ? 'error' : 'success'}`}
          role={notice.kind === 'error' ? 'alert' : 'status'}
          aria-live={notice.kind === 'error' ? 'assertive' : 'polite'}
        >
          {notice.text}
        </div>
      )}

      {canEdit && (
        <div className={styles.picker}>
          <label className="field" htmlFor="im-search">
            <span className={styles.pickerLabel}>Add a product</span>
            <input
              id="im-search"
              type="text"
              className="search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search the catalogue by name…"
              autoComplete="off"
            />
          </label>

          {query.trim().length >= 2 && (
            <div className={styles.results}>
              {searching && <p className={styles.hint}>Searching…</p>}
              {!searching && results.length === 0 && (
                <p className={styles.hint}>No products match that.</p>
              )}
              {results.map((product) => {
                const added = alreadyIn(product.id);
                return (
                  <button
                    key={product.id}
                    type="button"
                    className={styles.result}
                    onClick={() => addItem(product)}
                    disabled={added || busyId === product.id}
                    title={added ? 'Already in this ' + noun : undefined}
                  >
                    <span className={styles.resultName}>{product.name}</span>
                    <span className={styles.resultMeta}>
                      Rs. {product.price} / {product.unit}
                      {added && ' · already added'}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {items.length === 0 ? (
        <p className={styles.empty}>
          No items yet. {canEdit
            ? `Search above to add the samagri this ${noun} needs.`
            : `This ${noun} has no items.`}
        </p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Unit price</th>
                <th>Qty</th>
                <th>Required</th>
                {canEdit && <th>Action</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.product_name}</td>
                  <td>Rs. {item.product_price}</td>
                  <td>
                    {canEdit ? (
                      <input
                        type="number"
                        min="1"
                        step="1"
                        className={styles.qty}
                        defaultValue={item.quantity}
                        disabled={busyId === item.id}
                        aria-label={`Quantity of ${item.product_name}`}
                        // Commit on blur rather than on every keystroke, so typing
                        // "12" does not send a request for "1" first.
                        onBlur={(e) => {
                          const next = Number(e.target.value);
                          if (Number.isFinite(next) && next >= 1 && next !== item.quantity) {
                            patchItem(item, { quantity: next });
                          } else {
                            e.target.value = item.quantity;
                          }
                        }}
                      />
                    ) : (
                      item.quantity
                    )}
                  </td>
                  <td>
                    {canEdit ? (
                      <label className={styles.check}>
                        <input
                          type="checkbox"
                          checked={item.is_required}
                          disabled={busyId === item.id}
                          onChange={(e) => patchItem(item, { is_required: e.target.checked })}
                        />
                        <span>{item.is_required ? 'Required' : 'Optional'}</span>
                      </label>
                    ) : (
                      <span className={`badge ${item.is_required ? 'badge-success' : 'badge-neutral'}`}>
                        {item.is_required ? 'Required' : 'Optional'}
                      </span>
                    )}
                  </td>
                  {canEdit && (
                    <td>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => removeItem(item)}
                        disabled={busyId === item.id}
                      >
                        Remove
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!canEdit && (
        <p className={styles.hint}>
          You can view this {noun}, but only an administrator can change it.
        </p>
      )}
    </div>
  );
}
