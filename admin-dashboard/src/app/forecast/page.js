'use client';
import { useState, useEffect, useCallback, Fragment } from 'react';
import { api } from '@/lib/api';

const HORIZON_OPTIONS = [7, 14, 30, 60, 90];

// Tiny inline sparkline. No charting dependency: this is 30-90 points of
// integer data and a full chart library would be unjustified weight.
function Sparkline({ points, width = 120, height = 28 }) {
  if (!points || points.length < 2) return <span style={{ color: 'var(--text-gray)' }}>—</span>;

  const values = points.map(p => p.units);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;

  const coords = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = height - ((v - min) / span) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return (
    <svg width={width} height={height} style={{ display: 'block' }} aria-hidden="true">
      <polyline
        points={coords.join(' ')}
        fill="none"
        stroke="var(--primary)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MapeBadge({ mape }) {
  if (mape === null || mape === undefined) {
    return <span className="badge badge-neutral">n/a</span>;
  }
  // Coarse bands, stated as bands rather than false precision.
  if (mape < 15) return <span className="badge badge-success">{mape}%</span>;
  if (mape < 30) return <span className="badge badge-warning">{mape}%</span>;
  return <span className="badge badge-danger">{mape}%</span>;
}

export default function ForecastPage() {
  const [horizon, setHorizon] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async (h) => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`/analytics/demand-forecast/?horizon=${h}&limit=20`);
      setData(res);
    } catch (e) {
      setError(e.message || 'Failed to load the demand forecast.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(horizon); }, [horizon, load]);

  const agg = data?.aggregate;

  return (
    <div>
      <div className="header">
        <h1>Demand Forecast</h1>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <label htmlFor="horizon" style={{ fontSize: '0.85rem', color: 'var(--text-gray)' }}>
            Horizon
          </label>
          <select
            id="horizon"
            className="status-select"
            value={horizon}
            onChange={(e) => setHorizon(Number(e.target.value))}
          >
            {HORIZON_OPTIONS.map(h => (
              <option key={h} value={h}>{h} days</option>
            ))}
          </select>
        </div>
      </div>

      {/* Provenance banner. The model is fitted on generated data, and the UI
          says so at the top rather than burying it. */}
      {data?.is_synthetic && (
        <div className="notice" style={{ marginBottom: '20px', borderLeft: '4px solid #e65100' }}>
          <strong>Synthetic data — not real demand.</strong>{' '}
          {data.provenance_note}
        </div>
      )}

      {loading ? (
        <>
          <div className="grid grid-4" style={{ marginBottom: '30px' }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="card stat-card">
                <div className="skeleton-line" style={{ width: '45%' }} />
                <div className="skeleton-line" style={{ width: '70%', height: '2rem' }} />
              </div>
            ))}
          </div>
          <div className="card">
            <div className="skeleton-line" style={{ width: '30%', marginBottom: '16px' }} />
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="skeleton-line" style={{ width: '100%', marginBottom: '10px' }} />
            ))}
          </div>
        </>
      ) : error ? (
        <div className="card state-block state-error">
          <span className="state-icon">⚠️</span>
          <h3>Could not load the forecast</h3>
          <p>{error}</p>
          <button className="btn btn-outline" onClick={() => load(horizon)}>Try again</button>
        </div>
      ) : !data ? (
        <div className="card state-block">
          <span className="state-icon">📉</span>
          <h3>No forecast available</h3>
          <p>Run <code>python manage.py generate_synthetic_sales</code> to build the dataset.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-4" style={{ marginBottom: '30px' }}>
            <div className="card stat-card">
              <span className="stat-label">Forecast Demand</span>
              <span className="stat-value" style={{ color: 'var(--primary)' }}>
                {Math.round(agg?.total_forecast_units || 0).toLocaleString()}
              </span>
              <span className="badge badge-neutral">units over {data.horizon_days}d</span>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Products Covered</span>
              <span className="stat-value">{agg?.products_covered || 0}</span>
              <span className="badge badge-neutral">modelled items</span>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Need Restocking</span>
              <span className="stat-value" style={{ color: '#e65100' }}>
                {agg?.products_needing_restock || 0}
              </span>
              <span className="badge badge-warning" style={{ width: 'fit-content' }}>
                forecast exceeds stock
              </span>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Model Accuracy (MAPE)</span>
              <span className="stat-value">
                {agg?.mean_mape !== null && agg?.mean_mape !== undefined ? `${agg.mean_mape}%` : '—'}
              </span>
              <span className="badge badge-neutral">out-of-sample mean</span>
            </div>
          </div>

          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0 }}>Restock Priorities</h3>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-gray)' }}>
                {data.model?.name} · v{data.model?.version}
              </span>
            </div>

            {data.forecasts.length === 0 ? (
              <div className="state-inline">No products have enough history to forecast.</div>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                  <tr>
                    <th>Product</th>
                    <th>Stock</th>
                    <th>Forecast ({data.horizon_days}d)</th>
                    <th>Shortfall</th>
                    <th>Cover</th>
                    <th>Trend</th>
                    <th>MAPE</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {data.forecasts.map((f) => (
                    <Fragment key={f.product.id}>
                      <tr>
                        <td>
                          <strong>{f.product.name}</strong>
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-gray)' }}>
                            {f.product.category}
                          </div>
                        </td>
                        <td>{f.product.stock}</td>
                        <td><strong>{Math.round(f.forecast_total_units)}</strong></td>
                        <td>
                          {f.restock_needed
                            ? <span className="badge badge-danger">−{Math.round(f.projected_shortfall)}</span>
                            : <span className="badge badge-success">covered</span>}
                        </td>
                        <td>
                          {f.stock_cover_days === null
                            ? '—'
                            : `${f.stock_cover_days}d`}
                        </td>
                        <td><Sparkline points={f.predictions} /></td>
                        <td><MapeBadge mape={f.metrics?.mape} /></td>
                        <td>
                          <button
                            className="btn btn-outline"
                            style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                            onClick={() => setExpanded(expanded === f.product.id ? null : f.product.id)}
                          >
                            {expanded === f.product.id ? 'Hide' : 'Why?'}
                          </button>
                        </td>
                      </tr>
                      {expanded === f.product.id && (
                        <tr>
                          <td colSpan={8} style={{ background: '#fafafa' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', padding: '8px 4px' }}>
                              <div>
                                <strong style={{ fontSize: '0.85rem' }}>Model components</strong>
                                <table className="table" style={{ marginTop: '8px', fontSize: '0.82rem' }}>
                                  <tbody>
                                    <tr>
                                      <td>Baseline level</td>
                                      <td><strong>{f.components?.level}</strong> units/day</td>
                                    </tr>
                                    <tr>
                                      <td>Trend</td>
                                      <td>{f.components?.trend_slope_per_day >= 0 ? '+' : ''}{f.components?.trend_slope_per_day} /day</td>
                                    </tr>
                                    <tr>
                                      <td>Training days</td>
                                      <td>{f.components?.train_days}</td>
                                    </tr>
                                    <tr>
                                      <td>Festival lift</td>
                                      <td>×{f.components?.festival_lift} over {f.components?.festival_ramp_days}d</td>
                                    </tr>
                                  </tbody>
                                </table>
                              </div>
                              <div>
                                <strong style={{ fontSize: '0.85rem' }}>Weekday seasonality</strong>
                                <table className="table" style={{ marginTop: '8px', fontSize: '0.82rem' }}>
                                  <tbody>
                                    {Object.entries(f.components?.weekday_factors || {}).map(([day, factor]) => (
                                      <tr key={day}>
                                        <td>{day}</td>
                                        <td>
                                          <strong>{factor}</strong>
                                          {factor > 1.05 && <span style={{ color: '#2e7d32' }}> ↑</span>}
                                          {factor < 0.95 && <span style={{ color: '#c62828' }}> ↓</span>}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                            {f.metrics?.note && (
                              <p style={{ fontSize: '0.8rem', color: 'var(--text-gray)', marginTop: '10px' }}>
                                {f.metrics.note} MAE {f.metrics.mae}, RMSE {f.metrics.rmse}.
                              </p>
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
        </>
      )}
    </div>
  );
}
