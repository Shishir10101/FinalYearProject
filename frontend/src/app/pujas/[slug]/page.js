import Link from 'next/link';
import { notFound } from 'next/navigation';
import { festivalsAPI } from '@/lib/api';
import AddPujaButton from '@/components/AddPujaButton';
import styles from '../pujas.module.css';

export const dynamic = 'force-dynamic';

/** DRF serializes DecimalField as a string, so prices must be cast before maths. */
function money(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : '—';
}

/**
 * One ritual: the samagri it calls for, and its ready-made kit if one exists.
 *
 * A Server Component — the samagri lists are public data. Only the add-to-cart
 * button needs a client boundary, so it is extracted into `AddPujaButton`.
 *
 * An unknown slug calls `notFound()`, which renders the app's 404 UI. Note that it
 * does **not** return an HTTP 404: `src/app/pujas/loading.js` opens a Suspense
 * boundary, so the response has already started streaming by the time the fetch
 * resolves. Measured with curl, not assumed — see `src/app/not-found.js`.
 */
export default async function PujaDetailPage({ params }) {
  // Next 16: `params` is a Promise and must be awaited. Destructuring it directly
  // yields `undefined`, which would send every valid ritual to `notFound()`.
  // Verified against node_modules/next/dist/docs/01-app/.../03-layouts-and-pages.md.
  const { slug } = await params;

  let puja;
  try {
    puja = await festivalsAPI.pujaDetail(slug);
  } catch (e) {
    if (e?.status === 404) notFound();
    // Anything else is a genuine outage — rethrow so Next renders the error
    // boundary rather than pretending the ritual does not exist.
    console.error('Failed to load ritual:', e);
    throw e;
  }

  const items = puja.items || [];
  const required = items.filter((i) => i.is_required);
  const optional = items.filter((i) => !i.is_required);
  const requiredTotal = required.reduce(
    (sum, i) => sum + Number(i.product_detail?.price || 0) * i.quantity, 0
  );

  return (
    <div className="container section">
      <div className={styles.detailHeader}>
        <Link href="/pujas" className={styles.backLink}>← All rituals</Link>
        <h1 className={styles.detailTitle}>{puja.name}</h1>
        <div className={styles.detailMeta}>
          {puja.occasion_type && puja.occasion_type !== 'other' && (
            <span className="badge badge-secondary">{puja.occasion_display}</span>
          )}
          <span className={styles.count}>
            {required.length} essential
            {optional.length > 0 && <> · {optional.length} optional</>}
          </span>
        </div>
        {puja.description && <p className={styles.detailDesc}>{puja.description}</p>}
      </div>

      {items.length === 0 ? (
        <div className={styles.stateBlock}>
          <span aria-hidden="true">📿</span>
          <h3>No samagri listed for this ritual yet</h3>
          <p>
            We are still putting this list together. The catalogue is fully
            browsable in the meantime.
          </p>
          <Link href="/products" className="btn btn-primary mt-4">Browse products</Link>
        </div>
      ) : (
        <div className={styles.columns}>
          <div>
            <h2 className={styles.sectionHeading}>Essential samagri</h2>
            <p className={styles.sectionNote}>
              The items this ritual calls for. Quantities are what our kit uses.
            </p>
            <ul className={styles.itemList}>
              {required.map((item) => (
                <li key={item.id} className={styles.item}>
                  <Link
                    href={`/products/${item.product_detail?.slug || ''}`}
                    className={styles.itemName}
                  >
                    {item.product_detail?.name || 'Item'}
                  </Link>
                  <span className={styles.itemQty}>×{item.quantity}</span>
                  <span className={styles.itemPrice}>
                    Rs. {money(Number(item.product_detail?.price) * item.quantity)}
                  </span>
                </li>
              ))}
            </ul>

            {optional.length > 0 && (
              <>
                <h2 className={styles.sectionHeading}>Optional extras</h2>
                <p className={styles.sectionNote}>
                  Not needed for the ritual itself, but commonly added.
                </p>
                <ul className={styles.itemList}>
                  {optional.map((item) => (
                    <li key={item.id} className={`${styles.item} ${styles.optionalRow}`}>
                      <Link
                        href={`/products/${item.product_detail?.slug || ''}`}
                        className={styles.itemName}
                      >
                        {item.product_detail?.name || 'Item'}
                      </Link>
                      <span className={styles.itemQty}>×{item.quantity}</span>
                      <span className={styles.itemPrice}>
                        Rs. {money(Number(item.product_detail?.price) * item.quantity)}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          <aside className={styles.side}>
            <div className={styles.panel}>
              <p className={styles.panelTitle}>Essentials only</p>
              <div className={styles.totalRow}>
                <span className={styles.totalLabel}>{required.length} items</span>
                <span className={styles.totalValue}>Rs. {money(requiredTotal)}</span>
              </div>
              <AddPujaButton
                pujaId={puja.id}
                slug={puja.slug}
                itemCount={required.length}
              />
              <p className={styles.panelNote}>
                Adds the essential items only. Optional extras are never added for you.
              </p>
            </div>

            {puja.kit && (
              <div className={styles.kitPanel}>
                <p className={styles.panelTitle}>Ready-made kit</p>
                <p className={styles.kitPanelName}>{puja.kit.name}</p>
                <p className={styles.kitPanelNote}>
                  {puja.kit.item_count} items
                  {puja.kit.discount_percent > 0 && (
                    <> · {puja.kit.discount_percent}% off</>
                  )}
                  {' '}— Rs. {money(puja.kit.total_price)}
                </p>
                <Link
                  href={`/festivals?type=${puja.occasion_type || ''}`}
                  className="btn btn-outline"
                  style={{ width: '100%', display: 'block', textAlign: 'center' }}
                >
                  View the kit
                </Link>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
