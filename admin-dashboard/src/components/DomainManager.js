'use client';
import { useState, useEffect, useCallback, useMemo, Fragment } from 'react';
import { api, fieldErrors } from '@/lib/api';
import { useAdmin } from '@/context/AdminContext';
import Modal from '@/components/Modal';
import ConfirmDialog from '@/components/ConfirmDialog';
import ItemManager from '@/components/ItemManager';
import ImageField from '@/components/ImageField';
import styles from './DomainManager.module.css';

/**
 * A domain collection the dashboard can author: the list, the create/edit form,
 * the delete, and the nested item editor.
 *
 * Kits and rituals are the same shape at every level that matters — a name, a
 * type drawn from the same enum, a description, an active flag, and rows of
 * (product, quantity, is_required) behind a `/items/` sub-resource — and the
 * backend exposes both under parallel URLs. Writing this page twice is exactly
 * how the three product cards drifted apart before they were merged into
 * `ProductCard`, so there is one component and two configs.
 *
 * The config is expected to be a **module-level constant** in the page, not an
 * inline literal: it is a `useCallback` dependency, and a fresh object on every
 * render would re-run the initial fetch forever.
 *
 * @param {object} config
 * @param {string} config.heading          Page title.
 * @param {string} config.blurb            One line under the title.
 * @param {string} config.noun             Singular, for copy and for ItemManager.
 * @param {'kit'|'puja'} config.parentType Also the POST payload key.
 * @param {string} config.listUrl
 * @param {function} config.detailUrl      (id) => url
 * @param {function} [config.itemsUrl]     (id) => url. **Omit it** for a collection
 *                                         that has no item list — the Items control
 *                                         and its panel disappear.
 * @param {function} [config.itemUrl]      (id) => url, for ItemManager
 * @param {function} [config.displayName]  row => label for the edit title and the
 *                                         delete confirmation. Defaults to `row.name`,
 *                                         which not every model has (a `Vendor` has
 *                                         `shop_name`).
 * @param {object} config.lookups          { key: url } for select options.
 * @param {Array}  config.fields           Form descriptors. Each is
 *                                         `{ name, label, type, ... }` where type is
 *                                         `text` / `textarea` / `number` / `select` /
 *                                         `checkbox` / `image`. Add `createOnly: true` to
 *                                         offer a field when creating but freeze it when
 *                                         editing. An `image` field is not read from
 *                                         `form` — it renders the row's current picture
 *                                         and reports a new file (or its removal)
 *                                         separately, so `toForm`/`toPayload` need no
 *                                         `image` key.
 * @param {Array}  config.columns          { label, render(row) } table descriptors.
 * @param {function} config.matches        (row, query) => boolean, local filter.
 * @param {object} config.blank            Empty form values.
 * @param {function} config.toForm         row => form values.
 * @param {function} config.toPayload      form => API payload.
 * @param {string} config.emptyText
 * @param {string} config.newLabel
 * @param {string} config.createTitle        Title of the create dialog.
 * @param {string} config.searchPlaceholder
 * @param {string} config.itemHint         Copy shown above the item editor.
 * @param {string} config.deleteBody       Confirm-dialog copy (JSX).
 * @param {string} [config.activeField]    The boolean the enable/disable toggle
 *                                         writes. Defaults to `is_active`; a review
 *                                         carries `is_approved`.
 * @param {object} [config.activeLabels]   `{ on, off, onDone, offDone }` for the
 *                                         button and the confirmation flash.
 * @param {boolean} [config.canCreate]     Set `false` for a collection nobody authors
 *                                         — moderation has no "New review".
 * @param {boolean} [config.canEdit]       Set `false` to allow hide/delete only.
 */
export default function DomainManager({ config }) {
  const { isManager } = useAdmin();

  const noun = config.noun;

  /** Row label for the edit title and the delete flash. */
  const nameOf = (row) => (config.displayName ? config.displayName(row) : row.name);

  // A review is *hidden*, not deactivated: the flag it carries is `is_approved`. The
  // config names the field and the wording rather than the component guessing —
  // patching the wrong field returns 200 and changes nothing, which looks like it
  // worked until you reload.
  const activeField = config.activeField || 'is_active';
  const activeLabels = config.activeLabels
    || { on: 'Disable', off: 'Enable', onDone: 'deactivated', offDone: 'activated' };

  // Moderation is a different shape from authoring. A manager must be able to hide or
  // delete a customer's review but must not be able to write or rewrite one, so the
  // create and edit affordances are switched off rather than the page being forked.
  const allowCreate = config.canCreate !== false;
  const allowEdit = config.canEdit !== false;

  // A collection may have no item sub-resource at all (a vendor has products, not
  // items). Rather than fork the component, the Items control is simply absent —
  // an empty "Items" panel that always says "no items" would be worse than nothing.
  const hasItems = typeof config.itemsUrl === 'function';

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState(null);
  const [lookups, setLookups] = useState({});

  // dialog state: null | 'create' | row
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState({});
  const [form, setForm] = useState(config.blank);
  // Three-valued, exactly as on the products screen: `undefined` = untouched
  // (send JSON), a `File` = a new picture (send multipart), `null` = remove it
  // (send JSON `image: null`). Only used by a config that declares an `image`
  // field, so the four other configs are unaffected.
  const [imageFile, setImageFile] = useState(undefined);

  // the expanded row, and the items behind it
  const [expanded, setExpanded] = useState(null);
  const [items, setItems] = useState([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsError, setItemsError] = useState('');

  const fetchRows = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.get(config.listUrl);
      setRows(Array.isArray(data) ? data : (data.results || []));
    } catch (e) {
      setError(e.message || `Failed to load ${config.noun}s.`);
    } finally {
      setLoading(false);
    }
  }, [config]);

  // The enum behind both forms. Fetched rather than hardcoded — a type with no
  // kit yet must still be offerable, or the first kit of a new type could never
  // be created. Same reasoning as the old hardcoded CITY_CHOICES, reversed.
  const fetchLookups = useCallback(async () => {
    const entries = Object.entries(config.lookups || {});
    if (entries.length === 0) return;
    const results = await Promise.all(
      entries.map(async ([key, url]) => {
        try {
          const data = await api.get(url);
          return [key, Array.isArray(data) ? data : (data.results || [])];
        } catch {
          // A missing lookup degrades the form to an empty select; it must not
          // take the whole page down with it.
          return [key, []];
        }
      })
    );
    setLookups(Object.fromEntries(results));
  }, [config]);

  useEffect(() => { fetchRows(); }, [fetchRows]);
  useEffect(() => { fetchLookups(); }, [fetchLookups]);

  const flash = (text, kind = 'success') => {
    setNotice({ text, kind });
    setTimeout(() => setNotice(null), 4000);
  };

  const loadItems = useCallback(async (row) => {
    setItemsLoading(true);
    setItemsError('');
    try {
      const data = await api.get(config.itemsUrl(row.id));
      setItems(Array.isArray(data) ? data : (data.results || []));
    } catch (e) {
      setItemsError(e.message || 'Could not load the items.');
    } finally {
      setItemsLoading(false);
    }
  }, [config]);

  const toggleRow = (row) => {
    if (expanded === row.id) {
      setExpanded(null);
      setItems([]);
      setItemsError('');
      return;
    }
    setExpanded(row.id);
    loadItems(row);
  };

  // After any item write, both the item list and the row's counts are stale.
  const afterItemChange = async () => {
    const row = rows.find((r) => r.id === expanded);
    if (row) await loadItems(row);
    await fetchRows();
  };
  const openCreate = () => {
    setForm({ ...config.blank });
    setFormError({});
    setImageFile(undefined);
    setEditing('create');
  };

  const openEdit = (row) => {
    setForm(config.toForm(row));
    setFormError({});
    setImageFile(undefined);
    setEditing(row);
  };

  /**
   * Form payload → multipart parts.
   *
   * Same rules as the products screen: `null` becomes an empty part (DRF reads that
   * as "clear this nullable relation"), booleans become `'true'`/`'false'`, and
   * everything else is stringified.
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
    const isCreate = editing === 'create';
    const payload = config.toPayload(form);
    try {
      if (imageFile instanceof File) {
        await api.upload(
          isCreate ? config.listUrl : config.detailUrl(editing.id),
          toFormData(payload, imageFile),
          isCreate ? 'POST' : 'PATCH',
        );
      } else if (imageFile === null && !isCreate) {
        await api.patch(config.detailUrl(editing.id), { ...payload, image: null });
      } else if (isCreate) {
        await api.post(config.listUrl, payload);
      } else {
        await api.patch(config.detailUrl(editing.id), payload);
      }

      flash(`${config.noun[0].toUpperCase()}${config.noun.slice(1)} ${isCreate ? 'created' : 'updated'}.`);
      if (isCreate) {
        // A lookup can be *consumed* by a create — assigning a user to a shop
        // removes them from the "unassigned accounts" picker. Refetch so the form
        // cannot offer a choice the API would now reject.
        await fetchLookups();
      }
      setEditing(null);
      setImageFile(undefined);
      await fetchRows();
    } catch (e) {
      // `fieldErrors` keeps every message and guarantees a `_general` fallback,
      // so a rejection can never render as an empty dialog.
      setFormError(fieldErrors(e.body, e.message || `Could not save the ${config.noun}.`));
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    setBusy(true);
    try {
      await api.delete(config.detailUrl(deleting.id));
      flash(`“${nameOf(deleting)}” deleted.`);
      if (expanded === deleting.id) setExpanded(null);
      setDeleting(null);
      await fetchRows();
    } catch (e) {
      flash(e.message || `Could not delete the ${config.noun}.`, 'error');
      setDeleting(null);
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (row) => {
    // Optimistic, reconciled on failure.
    setRows((prev) =>
      prev.map((r) => (r.id === row.id ? { ...r, [activeField]: !r[activeField] } : r))
    );
    try {
      await api.patch(config.detailUrl(row.id), { [activeField]: !row[activeField] });
      flash(`“${nameOf(row)}” ${row[activeField] ? activeLabels.onDone : activeLabels.offDone}.`);
    } catch (e) {
      setRows((prev) =>
        prev.map((r) => (r.id === row.id ? { ...r, [activeField]: row[activeField] } : r))
      );
      flash(e.message || 'Could not update it.', 'error');
    }
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => config.matches(row, q));
  }, [rows, search, config]);

  /** Resolve a field's select options, from a lookup or an inline list. */
  const optionsFor = (field) => {
    const raw = field.optionsKey ? (lookups[field.optionsKey] || []) : (field.options || []);
    return raw.map((option) => (
      field.optionValue
        ? { value: option[field.optionValue], label: option[field.optionLabel] }
        : { value: option.value, label: option.label }
    ));
  };

  const renderField = (field) => {
    const id = `dm-${field.name}`;
    const value = form[field.name];
    const set = (next) => setForm((prev) => ({ ...prev, [field.name]: next }));
    const error = formError[field.name];
    // Some links are only settable at creation. Reassigning a shop's owning account
    // would silently transfer everything that account owns, so it is offered once
    // and then shown as fixed. `toPayload` still sends the original value.
    const frozen = Boolean(field.createOnly) && editing !== 'create';

    if (field.type === 'checkbox') {
      return (
        <label className="checkbox-field" key={field.name} htmlFor={id}>
          <input
            id={id}
            type="checkbox"
            checked={!!value}
            onChange={(e) => set(e.target.checked)}
          />
          {field.label}
        </label>
      );
    }

    // An image is not a value in `form` — it is a file (or a removal) reported
    // separately, so it is rendered from `editing` rather than from `form`. A config
    // that declares no `image` field never reaches this branch, so the four other
    // configs are untouched.
    if (field.type === 'image') {
      return (
        <ImageField
          key={field.name}
          label={field.label}
          currentUrl={editing !== 'create' ? editing.image : null}
          onSelect={setImageFile}
          disabled={busy}
          error={error}
          hint={field.hint}
        />
      );
    }

    return (
      <div className="field" key={field.name}>
        <label htmlFor={id}>{field.label}</label>
        {field.type === 'textarea' ? (
          <textarea
            id={id}
            value={value ?? ''}
            placeholder={field.placeholder}
            onChange={(e) => set(e.target.value)}
          />
        ) : field.type === 'select' ? (
          <select
            id={id}
            value={value ?? ''}
            disabled={frozen}
            onChange={(e) => set(e.target.value)}
          >
            <option value="">{field.emptyLabel || '— Select —'}</option>
            {optionsFor(field).map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        ) : (
          <input
            id={id}
            type={field.type === 'number' ? 'number' : 'text'}
            min={field.min}
            max={field.max}
            step={field.step}
            value={value ?? ''}
            placeholder={field.placeholder}
            disabled={frozen}
            onChange={(e) => set(e.target.value)}
          />
        )}
        {frozen && <span className="field-hint">Cannot be changed after creation.</span>}
        {field.hint && <span className="field-hint">{field.hint}</span>}
        {error && <span className="field-error">{error}</span>}
      </div>
    );
  };

  const inlineFields = config.fields.map((f) => f.name);

  return (
    <div>
      <div className="header">
        <div>
          <h1>{config.heading}</h1>
          {config.blurb && <p className={styles.blurb}>{config.blurb}</p>}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-outline" onClick={fetchRows} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          {isManager && allowCreate && (
            <button
              className="btn btn-primary"
              onClick={openCreate}
              disabled={loading || !!error}
            >
              {config.newLabel}
            </button>
          )}
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

      {!loading && !error && rows.length > 0 && (
        <div style={{ marginBottom: '16px' }}>
          <input
            type="text"
            className="search-input"
            placeholder={config.searchPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label={`Search ${config.noun}s`}
          />
        </div>
      )}

      <div className="card">
        {loading ? (
          <div>
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton-line" style={{ height: '38px' }} />
            ))}
          </div>
        ) : error ? (
          <div className="state-block state-error">
            <span className="state-icon">⚠️</span>
            <h3>Could not load {config.noun}s</h3>
            <p>{error}</p>
            <button className="btn btn-primary" style={{ marginTop: '16px' }} onClick={fetchRows}>
              Try again
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="state-inline">
            {search ? `Nothing matches “${search}”.` : config.emptyText}
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  {config.columns.map((column) => (
                    <th key={column.label}>{column.label}</th>
                  ))}
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <Fragment key={row.id}>
                    <tr>
                      {config.columns.map((column) => (
                        <td key={column.label}>{column.render(row)}</td>
                      ))}
                      <td>
                        <div className="row-actions">
                          {hasItems && (
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={() => toggleRow(row)}
                              aria-expanded={expanded === row.id}
                            >
                              {expanded === row.id ? 'Hide items' : 'Items'}
                            </button>
                          )}
                          {isManager && (
                            <>
                              {allowEdit && (
                                <button className="btn btn-ghost btn-sm" onClick={() => openEdit(row)}>
                                  Edit
                                </button>
                              )}
                              <button className="btn btn-ghost btn-sm" onClick={() => toggleActive(row)}>
                                {row[activeField] ? activeLabels.on : activeLabels.off}
                              </button>
                              <button className="btn btn-ghost btn-sm" onClick={() => setDeleting(row)}>
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>

                    {hasItems && expanded === row.id && (
                      <tr className="table-panel">
                        <td colSpan={config.columns.length + 1}>
                          {config.itemHint && (
                            <p className={styles.itemHint}>{config.itemHint}</p>
                          )}
                          {itemsLoading ? (
                            <div>
                              {[1, 2, 3].map((i) => (
                                <div key={i} className="skeleton-line" style={{ height: '30px' }} />
                              ))}
                            </div>
                          ) : itemsError ? (
                            <div className="state-inline state-error">
                              {itemsError}{' '}
                              <button
                                className="btn btn-ghost btn-sm"
                                onClick={() => loadItems(row)}
                              >
                                Retry
                              </button>
                            </div>
                          ) : (
                            <ItemManager
                              parentType={config.parentType}
                              parentId={row.id}
                              itemsUrl={config.itemsUrl(row.id)}
                              itemUrl={config.itemUrl}
                              items={items}
                              onChanged={afterItemChange}
                              canEdit={isManager}
                            />
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <Modal
          title={editing === 'create' ? config.createTitle : `Edit “${nameOf(editing)}”`}
          onClose={busy ? () => {} : () => setEditing(null)}
          wide
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => setEditing(null)} disabled={busy}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={submit} disabled={busy}>
                {busy ? 'Saving…' : editing === 'create' ? 'Create' : 'Save Changes'}
              </button>
            </>
          }
        >
          {formError._general && <div className="notice notice-error">{formError._general}</div>}

          {config.fields.map((field) => renderField(field))}

          {/*
            Safety net, same as the products modal: the server can reject
            something with no input on screen, and an error response must never
            leave the dialog open with no visible reason.
          */}
          {Object.entries(formError)
            .filter(([key]) => key !== '_general' && !inlineFields.includes(key))
            .map(([key, message]) => (
              <span key={key} className="field-error">{key}: {message}</span>
            ))}
        </Modal>
      )}

      {deleting && (
        <ConfirmDialog
          title={`Delete this ${config.noun}?`}
          body={config.deleteBody(deleting)}
          busy={busy}
          onConfirm={confirmDelete}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
