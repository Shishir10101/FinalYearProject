'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

const PRIORITY_STYLES = {
  critical: { background: '#ffebee', borderLeft: '4px solid #c62828' },
  high: { background: '#fff3e0', borderLeft: '4px solid #e65100' },
  medium: { background: '#e3f2fd', borderLeft: '4px solid #1976d2' },
  info: { background: '#fdf2f4', borderLeft: '4px solid var(--primary)' },
};

const PRIORITY_ICONS = {
  festival: '🗓️',
  inventory: '⚠️',
  restock: '📦',
  forecast_restock: '📈',
  trending: '🔥',
};

/**
 * The numbers on this page are **scope-dependent**, and the same page is served to
 * two different audiences:
 *
 *   * a manager (super admin / admin) sees the whole shop,
 *   * a vendor sees only orders containing their own products.
 *
 * `/analytics/sales/` and `/analytics/areas/` have both returned a `scope` field
 * since Day 9, and until now **nothing read it**. The route names are global
 * (`/analytics/sales/`), the panels are identical, and the Total Revenue card was
 * captioned `All time` for everyone — so a vendor was told, in the UI's own words,
 * that a vendor-scoped figure was their all-time shop revenue. The API was right the
 * whole time; the screen was the thing that lied.
 *
 * The scope is therefore derived from the **response**, never from the cached role.
 * If the two ever disagree the panel must describe what it actually fetched, not
 * what the client believes about itself.
 */
export default function Dashboard() {
  const [data, setData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [trending, setTrending] = useState([]);
  const [areaData, setAreaData] = useState(null);
  const [inventory, setInventory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const [sales, alertRes, trendRes, areaRes, invRes] = await Promise.all([
          api.get('/analytics/sales/'),
          api.get('/analytics/predictions/'),
          api.get('/analytics/trending/'),
          // Fetched with the rest rather than lazily: it is the same round-trip
          // budget and a panel that pops in after the others looks broken.
          api.get('/analytics/areas/'),
          // Routed since Day 2 with a full implementation and **no caller until
          // Day 15c** — no test either. See InventoryAnalyticsTests.
          api.get('/analytics/inventory/'),
        ]);
        if (cancelled) return;
        setData(sales);
        setAlerts(alertRes?.alerts || []);
        setTrending(Array.isArray(trendRes) ? trendRes.slice(0, 5) : []);
        setAreaData(areaRes);
        setInventory(invRes);
      } catch (e) {
        if (!cancelled) setError(e.message || 'Failed to load dashboard data.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div>
        <div className="header"><h1>Dashboard Overview</h1></div>
        <div className="grid grid-3" style={{ marginBottom: '30px' }}>
          {[1, 2, 3].map(i => (
            <div key={i} className="card stat-card">
              <div className="skeleton-line" style={{ width: '40%' }} />
              <div className="skeleton-line" style={{ width: '70%', height: '2rem' }} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <div className="header"><h1>Dashboard Overview</h1></div>
        <div className="card state-block state-error">
          <span className="state-icon">⚠️</span>
          <h3>Could not load the dashboard</h3>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const statusCounts = data?.status_counts || {};

  // Read from the payload; do not infer. `scope` is absent only if an older build
  // of the API is running, in which case we say so rather than guess.
  const scope = data?.scope || areaData?.scope || null;
  const isVendorScope = scope === 'vendor';

  return (
    <div>
      <div className="header">
        <h1>Dashboard Overview</h1>
        <div style={{ color: 'var(--text-gray)' }}>
          {new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}
        </div>
      </div>

      {scope && (
        // A vendor and a manager see the same layout with different totals and no
        // indication which is which. This states it outright, because "whose numbers
        // am I looking at" is not a question a dashboard should leave to a guess.
        <div
          className="card"
          data-testid="analytics-scope"
          data-scope={scope}
          style={{
            marginBottom: '24px', padding: '14px 18px',
            display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
            background: isVendorScope ? '#fff8e1' : 'var(--bg-secondary)',
            borderLeft: `4px solid ${isVendorScope ? '#e65100' : 'var(--primary)'}`,
          }}
        >
          <span className="badge badge-neutral" style={{ flex: '0 0 auto' }}>
            {isVendorScope ? 'Vendor scope' : 'Shop-wide'}
          </span>
          <p style={{ margin: 0, fontSize: '0.9rem' }}>
            {isVendorScope
              ? 'Every figure below counts only orders containing your own products, '
                + 'and stock figures cover only products you own. Anything you do not '
                + 'own is excluded.'
              : 'Every figure below covers the whole catalogue and every customer order.'}
          </p>
        </div>
      )}

      <div className="grid grid-4" style={{ marginBottom: '30px' }}>
        <div className="card stat-card">
          <span className="stat-label">Total Revenue</span>
          <span className="stat-value" style={{ color: 'var(--primary)' }}>
            Rs. {Number(data?.total_revenue || 0).toLocaleString()}
          </span>
          <span
            className="badge badge-neutral"
            data-testid="total-revenue-caption"
          >
            {/* Was the literal string "All time" for everyone, which described a
                vendor-scoped figure as their whole-shop all-time revenue. */}
            {isVendorScope ? 'Your products, all time' : 'All time'}
          </span>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Last 7 Days</span>
          <span className="stat-value">Rs. {Number(data?.revenue_7d || 0).toLocaleString()}</span>
          <span className="badge badge-neutral">{data?.orders_7d || 0} orders</span>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Total Orders</span>
          <span className="stat-value">{data?.total_orders || 0}</span>
          <span className="badge badge-neutral" data-testid="total-orders-caption">
            {data?.orders_30d || 0} in 30 days
          </span>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Pending Orders</span>
          <span className="stat-value" style={{ color: '#e65100' }}>{statusCounts.pending || 0}</span>
          <span className="badge badge-warning" style={{ width: 'fit-content' }}>Needs attention</span>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h3 style={{ marginBottom: '20px' }}>
            Orders by Status
            {isVendorScope && (
              <span className="badge badge-neutral" style={{ marginLeft: '8px', fontWeight: 400 }}>
                your products
              </span>
            )}
          </h3>
          {Object.keys(statusCounts).length === 0 ? (
            <div className="state-inline">No orders recorded yet.</div>
          ) : (
            <div className="table-wrap">
              <table className="table">
              <thead><tr><th>Status</th><th>Count</th></tr></thead>
              <tbody>
                {Object.entries(statusCounts).map(([status, count]) => (
                  <tr key={status}>
                    <td style={{ textTransform: 'capitalize' }}>{status}</td>
                    <td><strong>{count}</strong></td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginBottom: '20px' }}>Smart Prediction Alerts</h3>
          {alerts.length === 0 ? (
            <div className="state-inline">No alerts right now. Stock levels look healthy.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {alerts.slice(0, 5).map((a, i) => (
                <div key={i} style={{ padding: '12px', borderRadius: '6px', ...(PRIORITY_STYLES[a.priority] || PRIORITY_STYLES.info) }}>
                  <strong>{PRIORITY_ICONS[a.type] || '•'} {a.type?.toUpperCase()}</strong>
                  <p style={{ fontSize: '0.9rem', marginTop: '5px' }}>{a.message}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <h3>Orders by Delivery Area</h3>
          <Link href="/settings" className="btn btn-outline" style={{ padding: '5px 12px', fontSize: '0.8rem' }}>
            Manage areas
          </Link>
        </div>
        <p className="field-hint" style={{ marginTop: 0, marginBottom: '18px' }}>
          {isVendorScope
            ? <>Where orders containing <strong>your products</strong> are going. Rows
                sum to Total Revenue above, so the two figures always agree.</>
            : <>Where the Valley is ordering from. Rows sum to Total Revenue above, so the
                two figures always agree.</>}
        </p>

        {!areaData || areaData.areas.length === 0 ? (
          <div className="state-inline">No delivery areas configured yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
            <thead>
              <tr>
                <th>Area</th>
                <th>Orders</th>
                <th>Cancelled</th>
                <th>Revenue</th>
                <th style={{ width: '22%' }}>Share</th>
              </tr>
            </thead>
            <tbody>
              {areaData.areas.map((a) => (
                <tr key={a.slug}>
                  <td>
                    <strong>{a.name}</strong>
                    {!a.is_configured && (
                      // An order whose city no longer matches an Area row. Shown
                      // rather than dropped, or the rows would stop summing.
                      <span className="badge badge-warning" style={{ marginLeft: '6px' }}>
                        no longer configured
                      </span>
                    )}
                    {a.district && <div className="field-hint">{a.district}</div>}
                  </td>
                  <td>{a.orders}</td>
                  <td>
                    {a.cancelled_orders > 0
                      ? <span className="badge badge-danger">{a.cancelled_orders}</span>
                      : <span className="field-hint">—</span>}
                  </td>
                  <td>Rs. {a.revenue.toLocaleString()}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span
                        aria-hidden="true"
                        style={{
                          flex: '1 1 auto', height: '6px', borderRadius: '3px',
                          background: 'var(--bg-secondary)', overflow: 'hidden',
                          minWidth: '50px',
                        }}
                      >
                        <span
                          style={{
                            display: 'block', height: '100%',
                            width: `${Math.min(100, a.share_percent)}%`,
                            background: 'var(--primary)',
                          }}
                        />
                      </span>
                      <span style={{ fontSize: '0.8rem', minWidth: '38px' }}>
                        {a.share_percent}%
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
            </table>
          </div>
        )}
      </div>

      {inventory && (
        <div className="card" style={{ marginTop: '20px' }} data-testid="inventory-panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <h3>Stock Health</h3>
            <Link href="/products" className="btn btn-outline" style={{ padding: '5px 12px', fontSize: '0.8rem' }}>
              Edit stock
            </Link>
          </div>
          <p className="field-hint" style={{ marginTop: 0, marginBottom: '18px' }}>
            {/* The threshold is stated rather than implied: "Low Stock 0" is only
                reassuring if the reader knows what "low" means. */}
            Counted over {isVendorScope ? 'your active products' : 'all active products'}.
            A product is <strong>low</strong> below 10 units and <strong>out</strong> at 0,
            so out-of-stock items are also below the low threshold.
          </p>

          <div className="grid grid-3" style={{ marginBottom: inventory.low_stock_count > 0 ? '20px' : 0 }}>
            <div className="stat-card" style={{ padding: '12px 0' }}>
              <span className="stat-label">Units in stock</span>
              <span className="stat-value" style={{ fontSize: '1.5rem' }}>
                {Number(inventory.total_stock_units || 0).toLocaleString()}
              </span>
              <span className="badge badge-neutral">{inventory.total_products} products</span>
            </div>
            <div className="stat-card" style={{ padding: '12px 0' }}>
              <span className="stat-label">Low stock</span>
              <span className="stat-value" style={{ fontSize: '1.5rem', color: inventory.low_stock_count > 0 ? '#e65100' : 'inherit' }}>
                {inventory.low_stock_count}
              </span>
              <span className={`badge ${inventory.low_stock_count > 0 ? 'badge-warning' : 'badge-success'}`} style={{ width: 'fit-content' }}>
                {inventory.low_stock_count > 0 ? 'Needs attention' : 'Healthy'}
              </span>
            </div>
            <div className="stat-card" style={{ padding: '12px 0' }}>
              <span className="stat-label">Out of stock</span>
              <span className="stat-value" style={{ fontSize: '1.5rem', color: inventory.out_of_stock_count > 0 ? '#c62828' : 'inherit' }}>
                {inventory.out_of_stock_count}
              </span>
              <span className={`badge ${inventory.out_of_stock_count > 0 ? 'badge-danger' : 'badge-success'}`} style={{ width: 'fit-content' }}>
                {inventory.out_of_stock_count > 0 ? 'Unavailable' : 'None'}
              </span>
            </div>
          </div>

          {inventory.low_stock_products.length === 0 ? (
            // The demo catalogue's lowest stock is 25 units, so this branch is what
            // the shipped data actually shows. An empty panel that says nothing
            // would read as "broken"; saying *why* it is empty is the difference
            // between a healthy shop and a page that failed to load.
            <div className="state-inline" data-testid="inventory-all-healthy">
              Nothing is below the low-stock threshold of 10 units, so there is
              nothing to restock.
            </div>
          ) : (
            <div className="table-wrap">
              <table className="table">
              <thead>
                <tr>
                  <th>Product</th><th>Category</th><th>Stock</th><th>Price</th>
                </tr>
              </thead>
              <tbody>
                {inventory.low_stock_products.map((p) => (
                  <tr key={p.id} data-testid="low-stock-row">
                    <td><strong>{p.name}</strong></td>
                    <td>{p.category}</td>
                    <td>
                      {p.stock === 0
                        ? <span className="badge badge-danger">Out of stock</span>
                        : <span className="badge badge-warning">Low ({p.stock})</span>}
                    </td>
                    <td>Rs. {p.price}</td>
                  </tr>
                ))}
              </tbody>
              </table>
              {inventory.low_stock_count > inventory.low_stock_products.length && (
                <p className="field-hint" style={{ marginTop: '10px' }}>
                  Showing the {inventory.low_stock_products.length} lowest of{' '}
                  {inventory.low_stock_count} items below the threshold.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      <div className="card" style={{ marginTop: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3>Trending Products</h3>
          <Link href="/products" className="btn btn-outline" style={{ padding: '5px 12px', fontSize: '0.8rem' }}>
            Manage inventory
          </Link>
        </div>
        {trending.length === 0 ? (
          <div className="state-inline">No product activity yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
            <thead>
              <tr><th>Product</th><th>Category</th><th>Price</th><th>Stock</th><th>Demand Score</th></tr>
            </thead>
            <tbody>
              {trending.map(p => (
                <tr key={p.id}>
                  <td><strong>{p.name}</strong></td>
                  <td>{p.category}</td>
                  <td>Rs. {p.price}</td>
                  <td>
                    {p.stock === 0
                      ? <span className="badge badge-danger">Out of stock</span>
                      : p.stock < 10
                        ? <span className="badge badge-warning">Low ({p.stock})</span>
                        : <span className="badge badge-success">{p.stock}</span>}
                  </td>
                  <td><strong>{p.popularity_score}</strong></td>
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
