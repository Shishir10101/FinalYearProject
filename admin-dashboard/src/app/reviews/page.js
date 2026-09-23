'use client';
import DomainManager from '@/components/DomainManager';

/**
 * Review moderation.
 *
 * A customer's review publishes immediately (`is_approved` defaults to true), so the
 * manager's job here is the exception, not the queue: find something that should not
 * be on the storefront and hide or delete it. Pre-moderation was rejected deliberately
 * — on a shop with nobody on duty, every review being invisible until someone looks is
 * indistinguishable from the feature not working.
 *
 * Two things this page deliberately cannot do:
 *
 * * **No "New review".** A manager writing a review would be putting words in a
 *   customer's mouth. `canCreate: false` removes the affordance rather than letting the
 *   API reject it.
 * * **No "Edit".** Same reason — and the API marks `is_verified_purchase` read-only so
 *   even a direct PATCH cannot rewrite whether somebody had bought the thing.
 *
 * `is_approved` is not `is_active`, so the config names the field. Patching the wrong
 * one returns 200 and changes nothing, which looks like it worked until you reload.
 */
const REVIEW_CONFIG = {
  heading: 'Reviews',
  blurb:
    'Published reviews are visible immediately. Hide one to take it off the storefront '
    + 'without losing it; delete only when it should be gone for good.',
  noun: 'review',
  // No authoring: a manager moderates reviews, never writes them.
  canCreate: false,
  canEdit: false,
  listUrl: '/products/admin/reviews/',
  detailUrl: (id) => `/products/admin/reviews/${id}/`,
  displayName: (review) => `${review.product_name} — ${review.username}`,
  activeField: 'is_approved',
  activeLabels: {
    on: 'Hide',
    off: 'Show',
    onDone: 'hidden from the storefront',
    offDone: 'visible again',
  },
  searchPlaceholder: 'Search by product, reviewer or wording…',
  emptyText: 'No reviews have been written yet.',
  deleteBody: (review) => (
    <>
      <strong>{review.product_name}</strong> — the review by{' '}
      <strong>{review.username}</strong> will be permanently deleted, and the product&apos;s
      rating will be recalculated without it. This cannot be undone. To take it off the
      storefront but keep it, use <strong>Hide</strong> instead.
    </>
  ),

  // Unused: `canCreate` and `canEdit` are false, so no form is ever opened. Declared
  // empty rather than omitted so the component's contract is explicit.
  blank: {},
  toForm: () => ({}),
  toPayload: () => ({}),

  matches: (review, q) =>
    (review.product_name || '').toLowerCase().includes(q)
    || (review.username || '').toLowerCase().includes(q)
    || (review.title || '').toLowerCase().includes(q)
    || (review.body || '').toLowerCase().includes(q),

  fields: [],

  columns: [
    {
      label: 'Product',
      render: (review) => (
        <>
          <strong>{review.product_name}</strong>
          <div className="field-hint">/products/{review.product_slug}</div>
        </>
      ),
    },
    {
      label: 'Reviewer',
      render: (review) => (
        <>
          {review.username}
          {review.is_verified_purchase && (
            <span className="badge badge-success" style={{ marginLeft: '6px' }}>
              Verified
            </span>
          )}
        </>
      ),
    },
    {
      label: 'Rating',
      render: (review) => (
        <span style={{ whiteSpace: 'nowrap' }}>
          <span style={{ color: '#D4A843' }} aria-hidden="true">
            {'★'.repeat(review.rating)}
            <span style={{ color: '#d8d8d8' }}>{'★'.repeat(5 - review.rating)}</span>
          </span>{' '}
          <span className="field-hint">{review.rating}/5</span>
        </span>
      ),
    },
    {
      label: 'Review',
      render: (review) => (
        <>
          {review.title && <div style={{ fontWeight: 600 }}>{review.title}</div>}
          <div className="field-hint" style={{ maxWidth: '380px', whiteSpace: 'normal' }}>
            {review.body
              ? (review.body.length > 140 ? `${review.body.slice(0, 140)}…` : review.body)
              : '— no comment —'}
          </div>
        </>
      ),
    },
    {
      label: 'Visibility',
      render: (review) => (
        <span className={`badge ${review.is_approved ? 'badge-success' : 'badge-danger'}`}>
          {review.is_approved ? 'Published' : 'Hidden'}
        </span>
      ),
    },
  ],
};

export default function ReviewsPage() {
  return <DomainManager config={REVIEW_CONFIG} />;
}
