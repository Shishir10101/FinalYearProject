'use client';
import DomainManager from '@/components/DomainManager';

/**
 * Festival & Ritual Kits — the write surface for ready-made bundles.
 *
 * Until now this page was read-only: grep for a POST/PATCH/DELETE in it returned
 * nothing. The kits are a headline feature of the storefront, so the fact that
 * they could only be created or assembled in Django admin at `/admin/` was the
 * main hole in the dashboard.
 *
 * `ItemManager` already knew how to edit a kit's contents; this wires it in.
 * The list, the form and the delete flow come from `DomainManager`, which the
 * rituals page uses too.
 *
 * The config is a module-level constant on purpose — it is a `useCallback`
 * dependency inside `DomainManager`, so an inline literal would re-fetch on
 * every render.
 */
const KIT_CONFIG = {
  heading: 'Festival & Ritual Kits',
  blurb: 'A kit is one purchasable bundle. It declares which ritual it serves.',
  noun: 'kit',
  parentType: 'kit',
  newLabel: '+ New Kit',
  createTitle: 'New Kit',
  listUrl: '/festivals/admin/kits/',
  detailUrl: (id) => `/festivals/admin/kits/${id}/`,
  itemsUrl: (id) => `/festivals/admin/kits/${id}/items/`,
  itemUrl: (id) => `/festivals/admin/kit-items/${id}/`,
  lookups: {
    // The enum itself, so a festival type with no kit yet can still be chosen.
    festivalTypes: '/festivals/choices/',
    pujas: '/festivals/pujas/',
  },
  searchPlaceholder: 'Search kits by name or festival…',
  emptyText: 'No kits yet. Use “New Kit” to assemble the first one.',
  itemHint:
    'The samagri in this bundle. “Required” is the same flag the storefront shows '
    + 'as Required Samagri on the home page and on a ritual.',
  deleteBody: (kit) => (
    <>
      <strong>{kit.name}</strong> will be permanently removed, along with its{' '}
      {kit.item_count} item{kit.item_count === 1 ? '' : 's'}. This cannot be undone.
      If you only want to hide it from the storefront, use <strong>Disable</strong> instead.
    </>
  ),

  blank: {
    name: '',
    festival_type: '',
    description: '',
    discount_percent: 0,
    puja: '',
    is_active: true,
  },

  toForm: (kit) => ({
    name: kit.name ?? '',
    festival_type: kit.festival_type ?? '',
    description: kit.description ?? '',
    discount_percent: kit.discount_percent ?? 0,
    puja: kit.puja ?? '',
    is_active: kit.is_active !== false,
  }),

  // Empty strings must become null for the FK, and numbers must be numbers —
  // DRF rejects "12" for a PositiveIntegerField's min/max comparison silently
  // treating it as a string in some validators.
  toPayload: (form) => ({
    name: form.name,
    festival_type: form.festival_type,
    description: form.description,
    discount_percent: form.discount_percent === '' ? 0 : Number(form.discount_percent),
    puja: form.puja === '' ? null : Number(form.puja),
    is_active: !!form.is_active,
  }),

  matches: (kit, q) =>
    (kit.name || '').toLowerCase().includes(q)
    || (kit.festival_type || '').toLowerCase().includes(q),

  fields: [
    { name: 'name', label: 'Kit name', type: 'text', placeholder: 'e.g. Dashain Puja Complete Kit' },
    {
      name: 'festival_type',
      label: 'Festival / Ritual type',
      type: 'select',
      optionsKey: 'festivalTypes',
      emptyLabel: '— Select —',
      hint: 'The same vocabulary the calendar and the rituals use.',
    },
    {
      name: 'description',
      label: 'Description',
      type: 'textarea',
      placeholder: 'What the bundle contains and what it is used for.',
    },
    {
      name: 'discount_percent',
      label: 'Discount (%)',
      type: 'number',
      min: 0,
      max: 100,
      step: 1,
      hint: 'Applied to the sum of the item prices. 0 means no discount.',
    },
    {
      name: 'puja',
      label: 'Serves which ritual',
      type: 'select',
      optionsKey: 'pujas',
      optionValue: 'id',
      optionLabel: 'name',
      emptyLabel: '— Not linked —',
      hint: 'Optional. The link lives on the kit, so it is set from here.',
    },
    {
      name: 'image',
      label: 'Kit image',
      type: 'image',
      hint: 'Optional. Without one the storefront shows a placeholder lamp.',
    },
    { name: 'is_active', label: 'Visible in the storefront', type: 'checkbox' },
  ],

  columns: [
    {
      label: 'Kit',
      render: (kit) => (
        <>
          <strong>{kit.name}</strong>
          {kit.discount_percent > 0 && (
            <span className="badge badge-neutral" style={{ marginLeft: '6px' }}>
              {kit.discount_percent}% off
            </span>
          )}
          <div className="field-hint">id {kit.id}</div>
        </>
      ),
    },
    {
      label: 'Festival / Ritual',
      render: (kit) => (
        <span style={{ textTransform: 'capitalize' }}>
          {(kit.festival_type || '').replace(/_/g, ' ')}
        </span>
      ),
    },
    { label: 'Items', render: (kit) => kit.item_count },
    {
      label: 'Status',
      render: (kit) => (
        <span className={`badge ${kit.is_active ? 'badge-success' : 'badge-danger'}`}>
          {kit.is_active ? 'Active' : 'Inactive'}
        </span>
      ),
    },
  ],
};

export default function FestivalKitsPage() {
  return <DomainManager config={KIT_CONFIG} />;
}
