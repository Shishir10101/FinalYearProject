'use client';
import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { ordersAPI } from '@/lib/api';
import Link from 'next/link';

/**
 * Full order history.
 *
 * This route did not exist. The account dropdown in `Navbar` has linked to
 * `/account/orders` for as long as the menu has existed, and there was no page
 * behind it — clicking **My Orders** landed on the 404. `/account` shows the five
 * most recent orders and says "Recent Orders", so it was never the destination the
 * label promised.
 *
 * Found by the storefront browser check, not by the build or the API suite: a link
 * to a missing route compiles fine, returns a healthy page, and only misbehaves when
 * a person clicks it.
 *
 * The orders endpoint is paginated at `PAGE_SIZE = 12`, so this walks the pages
 * rather than showing a first page and pretending it is everything.
 */

const STATUS_BADGE = {
  delivered: 'badge-success',
  cancelled: 'badge-danger',
  pending: 'badge-warning',
};

export default function OrderHistoryPage() {
  const { user, loading: authLoading } = useAuth();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);

  const fetchPage = useCallback(async (nextPage, append) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError('');
    try {
      const data = await ordersAPI.listPage(nextPage);
      const rows = data.results || data || [];
      setOrders((prev) => (append ? [...prev, ...rows] : rows));
      setHasMore(Boolean(data.next));
      setPage(nextPage);
    } catch (e) {
      // Never render a backend failure as "you have no orders" — that tells the
      // customer something false about their own account.
      setError(e.message || 'Could not load your orders.');
      if (!append) setOrders([]);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setLoading(false);
      return;
    }
    fetchPage(1, false);
  }, [user, authLoading, fetchPage]);

  if (authLoading) {
    return (
      <div className="container section">
        <h1 className="section-title">My Orders</h1>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton-block" style={{ height: '110px', borderRadius: 'var(--radius-md)' }} />
          ))}
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="container section">
        <h1 className="section-title">My Orders</h1>
        <div className="empty-state">
          <div className="empty-state-icon">🔒</div>
          <h3 className="empty-state-title">Please log in</h3>
          <p className="empty-state-text">
            Your order history is tied to your account.
          </p>
          <Link
            href="/auth/login?redirect=/account/orders"
            className="btn btn-primary"
            style={{ marginTop: '16px', display: 'inline-block' }}
          >
            Log in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '12px', flexWrap: 'wrap' }}>
        <h1 className="section-title">My Orders</h1>
        <Link href="/account" style={{ fontSize: '0.9rem' }}>← Back to account</Link>
      </div>

      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', marginTop: '20px' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton-block" style={{ height: '110px', borderRadius: 'var(--radius-md)' }} />
          ))}
        </div>
      ) : error ? (
        <div className="empty-state" style={{ marginTop: '20px' }}>
          <div className="empty-state-icon">⚠️</div>
          <h3 className="empty-state-title">Could not load your orders</h3>
          <p className="empty-state-text">{error}</p>
          <button className="btn btn-primary" style={{ marginTop: '16px' }} onClick={() => fetchPage(1, false)}>
            Try again
          </button>
        </div>
      ) : orders.length === 0 ? (
        <div className="empty-state" style={{ marginTop: '20px' }}>
          <div className="empty-state-icon">🛍️</div>
          <h3 className="empty-state-title">No orders yet</h3>
          <p className="empty-state-text">
            When you place your first order it will appear here with live status tracking.
          </p>
          <Link href="/products" className="btn btn-primary" style={{ marginTop: '16px', display: 'inline-block' }}>
            Start shopping
          </Link>
        </div>
      ) : (
        <>
          <p style={{ color: 'var(--text-secondary)', marginTop: '4px' }}>
            {orders.length} order{orders.length === 1 ? '' : 's'} shown
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', marginTop: '12px' }}>
            {orders.map((order) => (
              <div
                key={order.id}
                className="card"
                style={{ padding: '18px', display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px', flexWrap: 'wrap' }}>
                    <strong>Order #{order.id}</strong>
                    <span className={`badge ${STATUS_BADGE[order.status] || 'badge-primary'}`}>
                      {order.status_display}
                    </span>
                  </div>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', margin: '2px 0' }}>
                    Placed {new Date(order.created_at).toLocaleString()}
                  </p>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', margin: '2px 0' }}>
                    Deliver to: <span style={{ textTransform: 'capitalize' }}>{order.shipping_city}</span>
                  </p>
                  {Array.isArray(order.items) && (
                    <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', margin: '2px 0' }}>
                      {order.items.length} item{order.items.length === 1 ? '' : 's'}
                      {order.items.length > 0 && (
                        <> · {order.items.map((i) => i.product_name).slice(0, 2).join(', ')}
                          {order.items.length > 2 ? ` +${order.items.length - 2} more` : ''}</>
                      )}
                    </p>
                  )}
                </div>

                <div style={{ textAlign: 'right', minWidth: '150px' }}>
                  <p style={{ fontSize: '1.15rem', fontWeight: 600, margin: '0 0 10px' }}>
                    Rs. {order.total_amount}
                  </p>
                  <Link href={`/account/orders/${order.id}`} className="btn btn-outline btn-sm">
                    View details
                  </Link>
                </div>
              </div>
            ))}
          </div>

          {hasMore && (
            <div style={{ textAlign: 'center', marginTop: '24px' }}>
              <button
                className="btn btn-outline"
                onClick={() => fetchPage(page + 1, true)}
                disabled={loadingMore}
              >
                {loadingMore ? 'Loading…' : 'Load older orders'}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
