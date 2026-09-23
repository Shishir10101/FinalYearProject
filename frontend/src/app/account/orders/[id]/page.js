'use client';
import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ordersAPI } from '@/lib/api';

/** Human-readable label for an Area slug, falling back to title case. */
function cityLabel(slug) {
  if (!slug) return '—';
  return slug.charAt(0).toUpperCase() + slug.slice(1);
}

/**
 * Format a step timestamp, or null when the step has no recorded time.
 *
 * The API returns `at: null` for a step it cannot date, and that must stay
 * visible rather than being papered over with the order's creation date — an
 * invented "delivered" time is worse than an honest blank.
 */
function formatStepTime(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function StatusTimeline({ timeline }) {
  if (!timeline?.steps?.length) return null;

  // Steps that already happened but carry no timestamp are the pre-tracking
  // orders. Say so once, instead of leaving the customer to wonder.
  const hasUndatedSteps = timeline.steps.some(
    (step) => step.state !== 'upcoming' && !step.at
  );

  return (
    <>
      <ol className="order-timeline">
        {timeline.steps.map((step, index) => {
          const time = formatStepTime(step.at);
          return (
            <li key={step.key} className={`order-step order-step-${step.state}`}>
              <span className="order-step-marker" aria-hidden="true">
                {step.state === 'done' ? '✓' : step.state === 'cancelled' ? '×' : index + 1}
              </span>
              <span className="order-step-label">{step.label}</span>
              {step.state !== 'upcoming' && (
                <span className="order-step-time">
                  {time || 'Time not recorded'}
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {hasUndatedSteps && (
        <p className="order-timeline-note">
          This order was placed before we started recording status times, so some
          steps show no timestamp.
        </p>
      )}
    </>
  );
}

export default function OrderDetailPage() {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchOrder = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await ordersAPI.detail(id);
      setOrder(data);
    } catch (e) {
      // Distinguish "this order does not exist / is not yours" from a transport
      // failure. The previous version collapsed both into "Order not found",
      // which told the customer the wrong thing when the server was simply down.
      setError(e.message || 'Could not load this order.');
      setOrder(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchOrder();
  }, [fetchOrder]);

  if (loading) {
    return (
      <div className="container section">
        <div className="skeleton-block" style={{ height: '32px', width: '220px', marginBottom: '20px' }} />
        <div className="grid grid-2">
          <div className="card" style={{ padding: '2rem' }}>
            <div className="skeleton-block" style={{ height: '120px' }} />
          </div>
          <div className="card" style={{ padding: '2rem' }}>
            <div className="skeleton-block" style={{ height: '120px' }} />
          </div>
        </div>
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="container section">
        <div style={{ marginBottom: '20px' }}>
          <Link href="/account">← Back to Account</Link>
        </div>
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">{error ? '⚠️' : '🔍'}</div>
            <h2 className="empty-state-title">
              {error ? 'Could not load this order' : 'Order not found'}
            </h2>
            <p className="empty-state-text">
              {error
                ? error
                : 'This order does not exist, or it belongs to a different account.'}
            </p>
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', marginTop: '20px' }}>
              <button className="btn btn-primary" onClick={fetchOrder}>Try again</button>
              <Link href="/account" className="btn btn-outline">Back to my orders</Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isCancelled = order.status === 'cancelled';

  return (
    <div className="container section">
      <div style={{ marginBottom: '20px' }}>
        <Link href="/account">← Back to Account</Link>
      </div>

      {/* Progress tracker */}
      <div className="card" style={{ padding: '1.5rem 2rem', marginBottom: '20px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '18px',
            flexWrap: 'wrap',
            gap: '8px',
          }}
        >
          <h2 style={{ fontSize: '1.05rem', margin: 0 }}>Order Progress</h2>
          <span className={`badge ${isCancelled ? 'badge-danger' : order.status === 'delivered' ? 'badge-success' : 'badge-primary'}`}>
            {order.status_display}
          </span>
        </div>
        <StatusTimeline timeline={order.timeline} />
        {isCancelled && (
          <p style={{ marginTop: '16px', marginBottom: 0, color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            This order was cancelled. If you were charged, the amount is refunded to the
            original payment method.
          </p>
        )}
      </div>

      <div className="grid grid-2">
        <div className="card" style={{ padding: '2rem' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '20px',
              borderBottom: '1px solid #eee',
              paddingBottom: '10px',
            }}
          >
            <h1 style={{ fontSize: '1.5rem', margin: 0 }}>Order #{order.id}</h1>
          </div>

          <div style={{ marginBottom: '20px', fontSize: '0.95rem', lineHeight: '1.8' }}>
            <p><strong>Placed on:</strong> {new Date(order.created_at).toLocaleString()}</p>
            <p>
              <strong>Payment Method:</strong> {order.payment_method_display}
              {order.payment_is_mocked && (
                <span
                  data-testid="payment-mocked-badge"
                  style={{
                    marginLeft: '8px', fontSize: '0.7rem', letterSpacing: '0.04em',
                    textTransform: 'uppercase', color: '#B45309',
                    border: '1px solid #B45309', borderRadius: '3px',
                    padding: '1px 5px',
                  }}
                >
                  Simulated
                </span>
              )}
            </p>
            <p>
              <strong>Payment Status:</strong>{' '}
              <span className={`badge ${order.payment_status === 'paid' ? 'badge-success' : 'badge-warning'}`}>
                {order.payment_status}
              </span>
            </p>
            {order.payment_is_mocked && (
              // The `paid` badge above is green and reads as a completed
              // transaction. Without this line the order detail is the single most
              // misleading screen in the app: it reports money as received when no
              // gateway was ever contacted. Explained rather than hidden, because
              // the demo genuinely does mark the order paid.
              <p
                role="note"
                style={{
                  border: '1px dashed #B45309', borderRadius: '8px',
                  padding: '10px 12px', margin: '10px 0 0',
                  fontSize: '0.85rem', color: 'var(--text-secondary)',
                  background: 'rgba(180,83,9,0.04)',
                }}
              >
                <strong>This is a demo order.</strong>{' '}
                {`"paid" above is simulated — ${order.payment_method_display} was not
                  contacted and no money changed hands. The order was confirmed so the
                  rest of the flow stays usable.`}
              </p>
            )}
          </div>

          <h3 style={{ fontSize: '1.2rem', marginBottom: '10px' }}>Shipping Details</h3>
          <div
            style={{
              background: 'var(--bg-secondary)',
              padding: '15px',
              borderRadius: '8px',
              fontSize: '0.95rem',
              lineHeight: '1.6',
            }}
          >
            <p>{order.shipping_address}</p>
            <p>{cityLabel(order.shipping_city)}</p>
            <p>Phone: {order.phone}</p>
            {order.notes && <p>Notes: {order.notes}</p>}
          </div>
        </div>

        <div className="card" style={{ padding: '2rem' }}>
          <h3
            style={{
              fontSize: '1.3rem',
              marginBottom: '15px',
              borderBottom: '1px solid #eee',
              paddingBottom: '10px',
            }}
          >
            Items ({order.items.length})
          </h3>

          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {order.items.map(item => (
              <li
                key={item.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '15px 0',
                  borderBottom: '1px dashed #eee',
                  gap: '12px',
                }}
              >
                <div>
                  {item.product ? (
                    <Link
                      href={`/products/${item.product}`}
                      style={{ fontWeight: '500', color: 'var(--text-primary)' }}
                    >
                      {item.product_name}
                    </Link>
                  ) : (
                    // The product was deleted after purchase. The order keeps its
                    // snapshot name and price, so the line is still meaningful.
                    <span style={{ fontWeight: '500', color: 'var(--text-secondary)' }}>
                      {item.product_name}
                    </span>
                  )}
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                    Rs. {item.price} × {item.quantity}
                  </div>
                </div>
                <strong style={{ alignSelf: 'center' }}>Rs. {item.subtotal}</strong>
              </li>
            ))}
          </ul>

          <div style={{ marginTop: '20px', borderTop: '2px solid #eee', paddingTop: '15px' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: '10px',
                color: 'var(--text-secondary)',
              }}
            >
              <span>Subtotal</span>
              <span>Rs. {order.subtotal}</span>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: '10px',
                color: 'var(--text-secondary)',
              }}
            >
              <span>Delivery Fee</span>
              <span>{Number(order.delivery_fee) === 0 ? 'Free' : `Rs. ${order.delivery_fee}`}</span>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '1.3rem',
                fontWeight: 'bold',
                color: 'var(--primary)',
                marginTop: '10px',
              }}
            >
              <span>Total</span>
              <span>Rs. {order.total_amount}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
