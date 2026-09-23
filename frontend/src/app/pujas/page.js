import Link from 'next/link';
import { festivalsAPI } from '@/lib/api';
import styles from './pujas.module.css';

export const dynamic = 'force-dynamic';

/**
 * Browse by ritual — the fourth discovery entry point.
 *
 * `AGENTS.md` §1 requires six: Product · Category · Festival · Puja · Samagri ·
 * Ready-made Kit. This page is the Puja one, and it is deliberately separate
 * from `/festivals`: a festival arrives on a date, whereas a rite of passage
 * happens when a family needs it, and a ritual can exist before anyone has
 * assembled a kit for it.
 *
 * A Server Component, like the home page. The data is entirely public, so
 * nothing here needs a token or a client boundary — which also means the page is
 * crawlable and its output can be verified without a browser.
 */
export default async function PujasPage() {
  let pujas = [];
  let loadFailed = false;

  try {
    const data = await festivalsAPI.pujas();
    pujas = Array.isArray(data) ? data : (data?.results || []);
  } catch (e) {
    // Surface a real error state rather than an empty grid, so a dead backend is
    // never mistaken for "there are no rituals".
    console.error('Failed to load rituals:', e);
    loadFailed = true;
  }

  return (
    <div className="container section">
      <div className={styles.hero}>
        <span className={styles.tagline}>Shop by Ritual</span>
        <h1 className={styles.title}>What are you performing?</h1>
        <p className={styles.subtitle}>
          Every ritual lists the samagri it calls for, with the essential items
          marked. Some have a ready-made kit; the rest you can assemble item by item.
        </p>
      </div>

      {loadFailed ? (
        <div className={styles.stateBlock}>
          <span aria-hidden="true">⚠️</span>
          <h3>Rituals are unavailable right now</h3>
          <p>We could not reach the store service. Please refresh in a moment.</p>
        </div>
      ) : pujas.length === 0 ? (
        <div className={styles.stateBlock}>
          <span aria-hidden="true">🙏</span>
          <h3>No rituals listed yet</h3>
          <p>Browse the catalogue in the meantime.</p>
          <Link href="/products" className="btn btn-primary mt-4">Browse products</Link>
        </div>
      ) : (
        <div className="grid grid-3">
          {pujas.map((puja) => (
            <Link href={`/pujas/${puja.slug}`} key={puja.id} className="card">
              <div className={styles.card}>
                <div className={styles.cardHead}>
                  {puja.occasion_type && puja.occasion_type !== 'other' && (
                    <span className="badge badge-secondary">{puja.occasion_display}</span>
                  )}
                  {puja.kit_id && <span className={styles.kitTag}>Ready-made kit</span>}
                </div>

                <h3>{puja.name}</h3>
                {puja.description && <p className={styles.desc}>{puja.description}</p>}

                <div className={styles.cardFoot}>
                  <span className={styles.count}>
                    {puja.required_count} essential
                    {puja.item_count > puja.required_count && (
                      <> · {puja.item_count - puja.required_count} optional</>
                    )}
                  </span>
                  <span className={styles.link}>See the samagri →</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
