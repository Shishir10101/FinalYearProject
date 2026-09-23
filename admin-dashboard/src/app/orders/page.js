'use client';
import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';

/**
 * When this order last moved, taken from its recorded status history.
 *
 * Returns an em dash when there is nothing recorded rather than falling back to
 * the order date, which would imply the order was actioned the moment it was
 * placed. Orders predating status tracking legitimately have no history.
 */
function lastChangeLabel(order) {
  const history = order.timeline?.history;
  if (!history?.length) return '—';
  const at = history[history.length - 1].at;
  if (!at) return '—';
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function OrdersPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  // Two different failures, deliberately kept apart.
  //
  // `loadError` means the list could not be fetched, so there is nothing to show and
  // replacing the table with an explanation is right.
  //
  // A **failed status write** is not that. It used to set this same `error` state, which
  // replaced the entire table with a block headed "Could not load orders" — a message
  // that was simply untrue (the list had loaded fine), while destroying the list the
  // admin was working through. One rejected write should cost one row's badge, not the
  // screen. Write outcomes go to `notice` instead, which the products screen already
  // does this way.
  const [loadError, setLoadError] = useState('');
  const [notice, setNotice] = useState(null);
  const [savingId, setSavingId] = useState(null);

  /**
   * Load the order list.
   *
   * `silent` refreshes the data **without** flipping `loading`, which matters after a
   * status write: the non-silent path replaces the whole table with skeletons, so
   * changing one order's status blanked the screen the admin was working through just
   * to update one "Last change" cell. The badge is already updated optimistically, so
   * the refresh only needs to correct that column.
   */
  const fetchOrders = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setLoadError('');
    try {
      const data = await api.get('/orders/admin/orders/');
      setOrders(data.results || data || []);
    } catch (e) {
      // A silent refresh must not turn a transient blip into a full-page error state
      // either — the table on screen is still valid data.
      if (!silent) setLoadError(e.message || 'Failed to load orders.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  // `fetchOrders` takes an options object, so it must not be handed a click event
  // directly — `onClick={fetchOrders}` would pass the event in as the options and
  // silently disable nothing while looking like it worked. `reload` is the event-safe
  // wrapper; every button uses that.
  const reload = useCallback(() => { fetchOrders(); }, [fetchOrders]);

  useEffect(() => { fetchOrders(); }, [fetchOrders]);

  // Self-clearing, matching `DomainManager` and the products screen, so a stale message
  // cannot sit above the table looking like it refers to whatever the reader just did.
  const flash = (text, kind = 'success') => {
    setNotice({ text, kind });
    setTimeout(() => setNotice(null), 4000);
  };

  const updateStatus = async (id, status) => {
    setSavingId(id);
    setNotice(null);
    try {
      await api.patch(`/orders/admin/orders/${id}/`, { status });
      setOrders(prev => prev.map(o => (o.id === id ? { ...o, status } : o)));
      flash(`Order #${id} updated to ${status}.`);
      // Refetch so the "Last change" column reflects the status event the server
      // just recorded, instead of showing the timestamp of the previous change.
      fetchOrders({ silent: true });
    } catch (e) {
      flash(e.message || `Failed to update order #${id}.`, 'error');
      // The server refused the change, so re-read the truth rather than leaving the row
      // showing something it rejected. (`setOrders` above runs only on success, so there
      // is no optimistic value to undo here — a "revert" would have been a no-op.)
      fetchOrders({ silent: true });
    } finally {
      setSavingId(null);
    }
  };

  const getStatusBadge = (status) => {
    if (status === 'delivered') return 'badge badge-success';
    if (status === 'pending') return 'badge badge-warning';
    if (status === 'cancelled') return 'badge badge-danger';
    return 'badge badge-neutral';
  };

  return (
    <div>
      <div className="header">
        <h1>Order Management</h1>
        <button className="btn btn-outline" onClick={reload} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
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

      <div className="card">
        {loading ? (
          <div>
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="skeleton-line" style={{ height: '38px' }} />
            ))}
          </div>
        ) : loadError ? (
          <div className="state-block state-error">
            <span className="state-icon">⚠️</span>
            <h3>Could not load orders</h3>
            <p>{loadError}</p>
            <button className="btn btn-primary" style={{ marginTop: '16px' }} onClick={reload}>
              Try again
            </button>
          </div>
        ) : orders.length === 0 ? (
          <div className="state-inline">No orders have been placed yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Date</th>
                <th>Amount</th>
                <th>City</th>
                <th>Payment</th>
                <th>Status</th>
                <th>Last change</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {orders.map(order => (
                <tr key={order.id}>
                  <td><strong>#{order.id}</strong></td>
                  <td>{new Date(order.created_at).toLocaleDateString('en-GB')}</td>
                  <td>Rs. {order.total_amount}</td>
                  <td style={{ textTransform: 'capitalize' }}>{order.shipping_city}</td>
                  <td style={{ textTransform: 'uppercase' }}>{order.payment_method}</td>
                  <td><span className={getStatusBadge(order.status)}>{order.status}</span></td>
                  <td>{lastChangeLabel(order)}</td>
                  <td>
                    <select
                      className="status-select"
                      value={order.status}
                      disabled={savingId === order.id}
                      onChange={(e) => updateStatus(order.id, e.target.value)}
                    >
                      <option value="pending">Pending</option>
                      <option value="confirmed">Confirmed</option>
                      <option value="processing">Processing</option>
                      <option value="shipped">Shipped</option>
                      <option value="delivered">Delivered</option>
                      <option value="cancelled">Cancelled</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
