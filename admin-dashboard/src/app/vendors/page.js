'use client';
import DomainManager from '@/components/DomainManager';

/**
 * Vendors — the shop-owning half of the role hierarchy.
 *
 * `core/permissions.py` defines four roles and the API has enforced vendor scoping
 * since Day 3, but there was no way to *administer* a vendor from the dashboard:
 * `/products/admin/vendors/` worked and nothing called it. A super admin could not
 * create a shop, assign it a delivery area, or close one down without going to
 * Django admin at `/admin/`.
 *
 * That also left one requirement from the original gap analysis unbuilt. It listed
 * "manage assigned area" alongside "manage areas" — and while areas became real
 * data on Day 3, *assigning one to a vendor* had no surface at all. `Vendor.area`
 * is the field, and it is on this form.
 *
 * No item list: a vendor owns products, not items, so `itemsUrl` is omitted and
 * `DomainManager` drops the Items control entirely.
 */
const VENDOR_CONFIG = {
  heading: 'Vendors',
  blurb:
    'A vendor is a login account plus a shop. Assigning an area sets the delivery '
    + 'zone the shop serves.',
  noun: 'vendor',
  newLabel: '+ New Vendor',
  createTitle: 'New Vendor',
  listUrl: '/products/admin/vendors/',
  detailUrl: (id) => `/products/admin/vendors/${id}/`,
  displayName: (vendor) => vendor.shop_name,
  lookups: {
    // Only accounts that do not already own a shop: `Vendor.user` is a
    // OneToOneField, so a second shop for the same account would be a 400.
    users: '/auth/admin/users/?unassigned=1',
    areas: '/products/admin/areas/',
  },
  searchPlaceholder: 'Search vendors by shop, owner or area…',
  emptyText: 'No vendors yet. Use “New Vendor” to add the first shop.',
  deleteBody: (vendor) => (
    <>
      <strong>{vendor.shop_name}</strong> will be removed. Its{' '}
      {vendor.product_count} product{vendor.product_count === 1 ? '' : 's'} will{' '}
      <strong>not</strong> be deleted — they become unassigned and stay in the
      catalogue. The account keeps its Vendor role, because revoking a login is a
      separate decision from closing a shop. This cannot be undone. To close the
      shop without unlinking its stock, use <strong>Disable</strong> instead.
    </>
  ),

  blank: {
    user: '',
    shop_name: '',
    area: '',
    phone: '',
    address: '',
    description: '',
    is_active: true,
  },

  toForm: (vendor) => ({
    user: vendor.user ?? '',
    shop_name: vendor.shop_name ?? '',
    area: vendor.area ?? '',
    phone: vendor.phone ?? '',
    address: vendor.address ?? '',
    description: vendor.description ?? '',
    is_active: vendor.is_active !== false,
  }),

  // Empty strings must become null for the FKs, not "".
  toPayload: (form) => ({
    user: form.user === '' ? null : Number(form.user),
    shop_name: form.shop_name,
    area: form.area === '' ? null : Number(form.area),
    phone: form.phone,
    address: form.address,
    description: form.description,
    is_active: !!form.is_active,
  }),

  matches: (vendor, q) =>
    (vendor.shop_name || '').toLowerCase().includes(q)
    || (vendor.user_username || '').toLowerCase().includes(q)
    || (vendor.area_name || '').toLowerCase().includes(q),

  fields: [
    {
      name: 'user',
      label: 'Owning account',
      type: 'select',
      optionsKey: 'users',
      optionValue: 'id',
      optionLabel: 'username',
      emptyLabel: '— Select an account —',
      createOnly: true,
      hint:
        'The login this shop belongs to. Creating the shop gives this account the '
        + 'Vendor role, which is what lets it open the dashboard.',
    },
    {
      name: 'shop_name',
      label: 'Shop name',
      type: 'text',
      placeholder: 'e.g. Patan Puja Bhandar',
    },
    {
      name: 'area',
      label: 'Assigned delivery area',
      type: 'select',
      optionsKey: 'areas',
      optionValue: 'id',
      optionLabel: 'name',
      emptyLabel: '— Not assigned —',
      hint: 'The zone this shop delivers in. Areas and their fees live in Catalog Settings.',
    },
    {
      name: 'phone',
      label: 'Phone',
      type: 'text',
      placeholder: '98XXXXXXXX',
    },
    {
      name: 'address',
      label: 'Address',
      type: 'textarea',
      placeholder: 'Street, ward, city.',
    },
    {
      name: 'description',
      label: 'Description',
      type: 'textarea',
      placeholder: 'What this shop sells, in one or two lines.',
    },
    { name: 'is_active', label: 'Trading (visible in the storefront)', type: 'checkbox' },
  ],

  columns: [
    {
      label: 'Shop',
      render: (vendor) => (
        <>
          <strong>{vendor.shop_name}</strong>
          {!vendor.is_active && (
            <span className="badge badge-danger" style={{ marginLeft: '6px' }}>
              Not trading
            </span>
          )}
          <div className="field-hint">/vendors/{vendor.slug}</div>
        </>
      ),
    },
    {
      label: 'Owner',
      render: (vendor) => vendor.user_username || <span className="field-hint">—</span>,
    },
    {
      label: 'Area',
      render: (vendor) =>
        vendor.area_name || <span className="field-hint">Not assigned</span>,
    },
    { label: 'Products', render: (vendor) => vendor.product_count },
    {
      label: 'Status',
      render: (vendor) => (
        <span className={`badge ${vendor.is_active ? 'badge-success' : 'badge-danger'}`}>
          {vendor.is_active ? 'Active' : 'Inactive'}
        </span>
      ),
    },
  ],
};

export default function VendorsPage() {
  return <DomainManager config={VENDOR_CONFIG} />;
}
