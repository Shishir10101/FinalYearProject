'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { festivalsAPI } from '@/lib/api';
import ProductCard from '@/components/ProductCard';
import styles from './recommendations.module.css';

// Human labels for the machine-readable reason codes emitted by the backend
// ranker (see backend/festivals/recommender.py::WEIGHTS).
const REASON_LABELS = {
  festival_required: 'Required for an upcoming festival',
  festival_optional: 'Optional extra for an upcoming festival',
  staple_samagri: 'Everyday puja essential',
  user_repeat: 'You have ordered this before',
  user_category: 'Matches your usual categories',
  user_kit_affinity: 'Goes with items you have bought',
  popular: 'Popular right now',
};

const URGENCY_LABEL = {
  urgent: 'Needed very soon',
  soon: 'Coming up soon',
  upcoming: 'Coming up',
};

function daysLabel(days) {
  if (days === null || days === undefined) return null;
  if (days < 0) return null;
  if (days === 0) return 'Today';
  if (days === 1) return 'Tomorrow';
  return `In ${days} days`;
}

export default function RecommendationsPage() {
  const [data, setData] = useState({
    upcoming_festivals: [],
    recommended_products: [],
    meta: null,
  });
  const [loading, setLoading] = useState(true);
  const [errorState, setErrorState] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const fetchRecommendations = async () => {
      try {
        const res = await festivalsAPI.recommendations();
        if (cancelled) return;
        setData({
          upcoming_festivals: res.upcoming_festivals || [],
          recommended_products: res.recommended_products || [],
          meta: res.meta || null,
        });
        setErrorState(null);
      } catch (e) {
        if (cancelled) return;
        console.error(e);
        setErrorState('We could not load your recommendations right now.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchRecommendations();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="container section">
      <div className={styles.hero}>
        <div className={styles.heroContent}>
          <span className={styles.tagline}>Smart Predictions</span>
          <h1 className={styles.title}>Recommended For You</h1>
          <p className={styles.subtitle}>
            Ranked by what the upcoming festival calendar requires, what you have
            bought before, and what the valley is buying most.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="card skeleton" style={{ height: '350px' }}></div>
          ))}
        </div>
      ) : errorState ? (
        <div className={styles.emptyState}>
          <span className={styles.emptyIcon}>⚠️</span>
          <h3>Recommendations are unavailable right now</h3>
          <p>{errorState}</p>
          <div style={{ marginTop: '20px', display: 'flex', gap: '15px', justifyContent: 'center' }}>
            <Link href="/products" className="btn btn-primary">Browse Products</Link>
            <Link href="/festivals" className="btn btn-outline">Festival Kits</Link>
          </div>
        </div>
      ) : (
        <>
          {data.upcoming_festivals.length > 0 && (
            <div className="animate-fadeInUp" style={{ animationDelay: '0.2s' }}>
              <h3 style={{
                marginBottom: '20px', fontSize: '1.4rem',
                color: 'var(--text-primary)', textAlign: 'center',
              }}>
                Approaching Festivals &amp; Rituals
              </h3>
              <div className={styles.festivalTags}>
                {data.upcoming_festivals.map(f => (
                  <Link
                    key={f.id}
                    href={`/festivals?type=${f.festival_type}`}
                    className={styles.festivalTag}
                  >
                    <span className={styles.festivalTagIcon}>🕉️</span>
                    <div>
                      <strong style={{ display: 'block', color: 'var(--primary)' }}>{f.name}</strong>
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        {new Date(f.date).toLocaleDateString('en-US', {
                          weekday: 'long', month: 'short', day: 'numeric',
                        })}
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {data.recommended_products.length > 0 ? (
            <>
              {data.meta && (
                <p className={styles.modelNote} style={{
                  textAlign: 'center', color: 'var(--text-secondary)',
                  fontSize: '0.9rem', marginBottom: '24px',
                }}>
                  {data.meta.personalised
                    ? 'Personalised from your order history.'
                    : 'Sign in to personalise these results with your order history.'}
                </p>
              )}

              <div className="grid grid-4 animate-fadeInUp" style={{ animationDelay: '0.4s' }}>
                {data.recommended_products.map(product => {
                  const rec = product.recommendation || {};
                  const topReason = (rec.reasons || [])[0];

                  return (
                    <ProductCard
                      key={product.id}
                      product={product}
                      badge={rec.urgency === 'urgent' ? (daysLabel(rec.days_until) || 'Needed soon') : undefined}
                      // Rendered from the backend's reason list, never invented here.
                      reason={
                        topReason
                          ? (topReason.text || REASON_LABELS[topReason.code] || 'Recommended for you')
                          : undefined
                      }
                    />
                  );
                })}
              </div>
            </>
          ) : (
            <div className={styles.emptyState}>
              <span className={styles.emptyIcon}>🙏</span>
              <h3>No specific recommendations right now</h3>
              <p>Check out our complete catalog or explore our pre-made festival kits.</p>
              <div style={{ marginTop: '20px', display: 'flex', gap: '15px', justifyContent: 'center' }}>
                <Link href="/products" className="btn btn-primary">Browse Products</Link>
                <Link href="/festivals" className="btn btn-outline">Festival Kits</Link>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
