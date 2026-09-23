'use client';
import DomainManager from '@/components/DomainManager';

/**
 * Rituals (Pujas) — the authoring surface for the Puja entry point.
 *
 * This page did not exist. `Puja` had public read endpoints and (since the first
 * half of Day 8) write endpoints, but nothing in the dashboard called them, so
 * the ritual half of the domain could only be edited in Django admin at
 * `/admin/`.
 *
 * It is `DomainManager` with a different config rather than a second page: the
 * two collections differ only in which fields they carry, and the item editor
 * behind them is literally the same component.
 *
 * One asymmetry is deliberate and is stated in the UI rather than hidden: a
 * ritual **cannot** be given a kit from here. The link is a FK on the kit
 * (`FestivalKit.puja`), because a kit declares which ritual it serves and one
 * ritual may legitimately have several bundles — so the kit form is where it is
 * set, and this page only reports what is already attached.
 */
const PUJA_CONFIG = {
  heading: 'Rituals (Pujas)',
  blurb:
    'A ritual is what a ceremony requires. A ready-made kit is one bundle that '
    + 'serves it — link a kit from the Festival & Ritual Kits page.',
  noun: 'ritual',
  parentType: 'puja',
  newLabel: '+ New Ritual',
  createTitle: 'New Ritual',
  listUrl: '/festivals/admin/pujas/',
  detailUrl: (id) => `/festivals/admin/pujas/${id}/`,
  itemsUrl: (id) => `/festivals/admin/pujas/${id}/items/`,
  itemUrl: (id) => `/festivals/admin/puja-items/${id}/`,
  lookups: {
    festivalTypes: '/festivals/choices/',
  },
  searchPlaceholder: 'Search rituals by name or occasion…',
  emptyText: 'No rituals yet. Use “New Ritual” to add the first one.',
  itemHint:
    'The samagri this ritual calls for. This list is the ritual requirement, not '
    + 'a merchandising choice — it is deliberately separate from any kit’s items.',
  deleteBody: (puja) => (
    <>
      <strong>{puja.name}</strong> and its {puja.item_count} samagri row
      {puja.item_count === 1 ? '' : 's'} will be permanently removed. This cannot be
      undone.
      {puja.kit_count > 0 && (
        <>
          {' '}Its {puja.kit_count} linked kit{puja.kit_count === 1 ? '' : 's'} (
          {puja.kit_names.join(', ')}) will <strong>not</strong> be deleted — they
          simply stop pointing at a ritual.
        </>
      )}
      {' '}If you only want to hide it from the storefront, use <strong>Disable</strong> instead.
    </>
  ),

  blank: {
    name: '',
    occasion_type: '',
    description: '',
    is_active: true,
  },

  toForm: (puja) => ({
    name: puja.name ?? '',
    occasion_type: puja.occasion_type ?? '',
    description: puja.description ?? '',
    is_active: puja.is_active !== false,
  }),

  // `occasion_type` is blank-able on the model, so '' is accepted; the slug is
  // derived server-side and must not be sent.
  toPayload: (form) => ({
    name: form.name,
    occasion_type: form.occasion_type,
    description: form.description,
    is_active: !!form.is_active,
  }),

  matches: (puja, q) =>
    (puja.name || '').toLowerCase().includes(q)
    || (puja.occasion_type || '').toLowerCase().includes(q),

  fields: [
    { name: 'name', label: 'Ritual name', type: 'text', placeholder: 'e.g. Satyanarayan Puja' },
    {
      name: 'occasion_type',
      label: 'Occasion',
      type: 'select',
      optionsKey: 'festivalTypes',
      emptyLabel: '— Not linked to an occasion —',
      hint: 'Optional. The same vocabulary the calendar and the kits use.',
    },
    {
      name: 'description',
      label: 'Description',
      type: 'textarea',
      placeholder: 'What the ritual is for, and what it involves.',
    },
    { name: 'is_active', label: 'Visible in the storefront', type: 'checkbox' },
  ],

  columns: [
    {
      label: 'Ritual',
      render: (puja) => (
        <>
          <strong>{puja.name}</strong>
          <div className="field-hint">/pujas/{puja.slug}</div>
        </>
      ),
    },
    {
      label: 'Occasion',
      render: (puja) => (
        <span style={{ textTransform: 'capitalize' }}>
          {(puja.occasion_type || '').replace(/_/g, ' ') || '—'}
        </span>
      ),
    },
    { label: 'Samagri', render: (puja) => puja.item_count },
    {
      label: 'Served by',
      render: (puja) =>
        puja.kit_count === 0 ? (
          // Not a problem — 3 of the 8 seeded rituals have no kit, and a ritual
          // has to be able to exist before anyone assembles one.
          <span className="field-hint">No kit yet</span>
        ) : (
          puja.kit_names.join(', ')
        ),
    },
    {
      label: 'Status',
      render: (puja) => (
        <span className={`badge ${puja.is_active ? 'badge-success' : 'badge-danger'}`}>
          {puja.is_active ? 'Active' : 'Inactive'}
        </span>
      ),
    },
  ],
};

export default function RitualsPage() {
  return <DomainManager config={PUJA_CONFIG} />;
}
