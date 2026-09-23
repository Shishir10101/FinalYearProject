import Link from 'next/link';
import { productsAPI, festivalsAPI } from '@/lib/api';
import ProductCard from '@/components/ProductCard';
import styles from './page.module.css';

export const dynamic = 'force-dynamic';

/**
 * Whole days from today until a date-only string, ignoring time of day.
 *
 * Computed from the calendar parts rather than by subtracting timestamps: the
 * server's timezone is not guaranteed to match the browser's, and a raw
 * difference would report "in 0 days" for a festival that is still tomorrow.
 */
function daysUntil(dateStr) {
  const target = new Date(`${dateStr}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date();
  const a = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const b = Date.UTC(target.getFullYear(), target.getMonth(), target.getDate());
  return Math.round((b - a) / 86400000);
}

function countdownLabel(days) {
  if (days === null) return null;
  if (days < 0) return null;
  if (days === 0) return 'Today';
  if (days === 1) return 'Tomorrow';
  return `In ${days} days`;
}

function formatFestivalDate(dateStr) {
  const date = new Date(`${dateStr}T00:00:00`);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'long',
  });
}

export default async function Home() {
  // Public endpoints only, so a Server Component is safe here — nothing depends
  // on a token. On failure we surface an explicit "unavailable" state rather
  // than inventing fallback content, so a dead backend is never mistaken for a
  // working one.
  let featuredProducts = [];
  let recommendations = [];
  let recMeta = null;
  let upcomingFestivals = [];
  let kits = [];
  let pujas = [];
  let requiredItems = [];
  let loadFailed = false;

  try {
    const [productsRes, recRes, upcomingRes, kitsRes, pujasRes] = await Promise.all([
      productsAPI.featured(),
      festivalsAPI.recommendations(),
      festivalsAPI.upcoming(6),
      festivalsAPI.kits(),
      // The ritual entry point. Public, so safe from a Server Component.
      festivalsAPI.pujas(),
    ]);

    featuredProducts = Array.isArray(productsRes) ? productsRes : [];
    recommendations = recRes?.recommended_products || [];
    recMeta = recRes?.meta || null;
    upcomingFestivals = Array.isArray(upcomingRes) ? upcomingRes : [];
    kits = Array.isArray(kitsRes) ? kitsRes : (kitsRes?.results || []);
    pujas = Array.isArray(pujasRes) ? pujasRes : (pujasRes?.results || []);
  } catch (e) {
    console.error('Failed to load home data:', e);
    loadFailed = true;
  }

  // The soonest festival drives the spotlight. `/festivals/upcoming/` is already
  // ordered soonest-first, so the first entry is the one to lead with.
  const nextFestival = upcomingFestivals[0] || null;
  const nextDays = nextFestival ? daysUntil(nextFestival.date) : null;

  // A kit exists only for some festival types — Ganesh Chaturthi, Haritalika Teej
  // and Indra Jatra have none — so the spotlight has to cope with that rather
  // than assume a kit is always there.
  const matchingKit = nextFestival
    ? kits.find((kit) => kit.festival_type === nextFestival.festival_type)
    : null;

  // Required samagri is the point of the domain model, so the panel must not sit
  // empty just because the very next festival happens to be kitless. When that is
  // the case it follows the nearest festival that *does* have a kit, and names it,
  // rather than showing an unlabelled list or nothing at all.
  const kitFestival = matchingKit
    ? nextFestival
    : upcomingFestivals.find(
        (festival) => kits.some((kit) => kit.festival_type === festival.festival_type)
      ) || null;
  const panelKit = matchingKit
    || (kitFestival
      ? kits.find((kit) => kit.festival_type === kitFestival.festival_type)
      : null);

  // Only the panel needs kit *detail*; the spotlight's kit box is served by the
  // summary already in `kits`. Keeping the two separate matters: sharing one
  // variable made the spotlight offer "Get this kit" for a festival that has none.
  if (panelKit) {
    try {
      const detail = await festivalsAPI.kitDetail(panelKit.id);
      // `is_required` is the Required Samagri mechanism — surfacing it here is
      // the point of the panel, so only required items are listed.
      requiredItems = (detail.items || []).filter((item) => item.is_required);
    } catch (e) {
      // A missing kit detail must not take the whole page down; the panel simply
      // does not render.
      console.error('Failed to load kit detail:', e);
    }
  }

  const topRecommendations = recommendations.slice(0, 4);
  const calendarFestivals = upcomingFestivals.slice(0, 4);

  return (
    <div className={styles.home}>
      {/* Hero */}
      <section className={styles.hero}>
        <div className="container">
          <div className={styles.heroContent}>
            {nextFestival && nextDays !== null && nextDays >= 0 ? (
              <span className="badge badge-secondary mb-2">
                {nextFestival.name} · {countdownLabel(nextDays)}
              </span>
            ) : (
              <span className="badge badge-secondary mb-2">Kathmandu Valley&apos;s own</span>
            )}
            <h1 className="animate-fadeInUp">Your Complete <br/>
              <span className={styles.highlight}>Puja Sewa</span> Store
            </h1>
            <p className="animate-fadeInUp" style={{ animationDelay: '0.2s' }}>
              From daily rituals to grand festivals, find all your authentic puja requirements in one place. Fast delivery across Kathmandu, Lalitpur, and Bhaktapur.
            </p>
            <div className={`${styles.heroActions} animate-fadeInUp`} style={{ animationDelay: '0.4s' }}>
              <Link href="/festivals" className="btn btn-primary btn-lg">
                Festival Kits
              </Link>
              <Link href="/recommendations" className="btn btn-outline btn-lg">
                What do I need?
              </Link>
            </div>
            <div className={`${styles.features} animate-fadeInUp`} style={{ animationDelay: '0.6s' }}>
              <div className={styles.feature}>
                <span aria-hidden="true">🕉️</span> 100% Authentic
              </div>
              <div className={styles.feature}>
                <span aria-hidden="true">🚚</span> Next Day Delivery
              </div>
              <div className={styles.feature}>
                <span aria-hidden="true">💐</span> Fresh Items
              </div>
            </div>
          </div>
        </div>
        <div className={styles.heroPattern}></div>
      </section>

      {/* Next festival spotlight — the festival calendar leads, not a product grid */}
      {nextFestival && (
        <section className={`section ${styles.spotlight}`}>
          <div className="container">
            <div className={styles.spotlightInner}>
              <div className={styles.spotlightMain}>
                <span className={styles.spotlightEyebrow}>Next festival</span>
                <h2 className={styles.spotlightTitle}>{nextFestival.name}</h2>
                <p className={styles.spotlightMeta}>
                  {formatFestivalDate(nextFestival.date)}
                  {nextDays !== null && nextDays >= 0 && (
                    <> · <strong>{countdownLabel(nextDays)}</strong></>
                  )}
                </p>
                {nextFestival.description && (
                  <p className={styles.spotlightDesc}>{nextFestival.description}</p>
                )}

                {matchingKit ? (
                  <div className={styles.kitBox}>
                    <div>
                      <strong>{matchingKit.name}</strong>
                      <p className={styles.kitMeta}>
                        {matchingKit.item_count} items
                        {matchingKit.id === panelKit?.id && requiredItems.length > 0
                          && ` · ${requiredItems.length} required`}
                      </p>
                    </div>
                    <div className={styles.kitPrice}>
                      <span className={styles.kitPriceNow}>Rs. {matchingKit.total_price}</span>
                      {matchingKit.original_price
                        && matchingKit.original_price !== matchingKit.total_price && (
                        <span className={styles.kitPriceWas}>Rs. {matchingKit.original_price}</span>
                      )}
                    </div>
                    <Link href={`/festivals?type=${nextFestival.festival_type}`} className="btn btn-primary">
                      Get this kit
                    </Link>
                  </div>
                ) : (
                  // Honest: no ready-made kit exists for this festival yet. Say so
                  // and route the shopper somewhere useful instead of showing an
                  // empty slot or an unrelated kit.
                  <div className={styles.noKit}>
                    <p>
                      We do not have a ready-made kit for {nextFestival.name} yet.
                    </p>
                    <Link href="/recommendations" className="btn btn-outline">
                      See what you will need
                    </Link>
                  </div>
                )}
              </div>

              {requiredItems.length > 0 && kitFestival && (
                <aside className={styles.requiredPanel}>
                  {/* Names the festival it belongs to, because when the nearest
                      festival is kitless this list is for a later one. */}
                  <h3 className={styles.requiredHeading}>
                    Required samagri
                  </h3>
                  <p className={styles.requiredFor}>
                    For {kitFestival.name}
                    {daysUntil(kitFestival.date) !== null && (
                      <> · {countdownLabel(daysUntil(kitFestival.date))}</>
                    )}
                  </p>
                  <ul className={styles.requiredList}>
                    {requiredItems.slice(0, 7).map((item) => (
                      <li key={item.id}>
                        <Link href={`/products/${item.product_detail?.slug || ''}`}>
                          <span>{item.product_detail?.name || 'Item'}</span>
                          <span className={styles.requiredPrice}>
                            Rs. {item.product_detail?.price}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                  {requiredItems.length > 7 && (
                    <p className={styles.requiredMore}>
                      +{requiredItems.length - 7} more in the kit
                    </p>
                  )}
                  <Link
                    href={`/festivals?type=${kitFestival.festival_type}`}
                    className={styles.requiredCta}
                  >
                    View the full kit →
                  </Link>
                </aside>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Recommended for you — the recommendation engine, on the front page */}
      <section className="section bg-secondary">
        <div className="container">
          <div className={styles.sectionHeader}>
            <div>
              <h2 className="section-title">Recommended For You</h2>
              <p className="section-subtitle">
                Ranked against the festival calendar, each with the reason it was chosen
              </p>
            </div>
            <Link href="/recommendations" className="btn btn-outline">See all</Link>
          </div>

          {topRecommendations.length > 0 ? (
            <div className="grid grid-4">
              {topRecommendations.map((product) => {
                const reason = (product.recommendation?.reasons || [])[0];
                const days = product.recommendation?.days_until;
                return (
                  <ProductCard
                    key={product.id}
                    product={product}
                    reason={reason?.text}
                    badge={product.recommendation?.urgency === 'urgent'
                      ? countdownLabel(days) || 'Needed soon'
                      : undefined}
                  />
                );
              })}
            </div>
          ) : (
            <div className={loadFailed ? styles.errorState : styles.emptyState}>
              <span aria-hidden="true">{loadFailed ? '⚠️' : '🙏'}</span>
              <h3>{loadFailed ? 'Recommendations are unavailable right now' : 'Nothing to recommend yet'}</h3>
              <p>
                {loadFailed
                  ? 'We could not reach the store service. Please refresh in a moment.'
                  : 'Browse the catalogue while we put together suggestions for you.'}
              </p>
              <Link href="/products" className="btn btn-primary mt-4">Browse products</Link>
            </div>
          )}
        </div>
      </section>

      {/* Festival calendar */}
      <section className="section">
        <div className="container">
          <div className={styles.sectionHeader}>
            <div>
              <h2 className="section-title">The Festival Calendar</h2>
              <p className="section-subtitle">Plan ahead — we stock for each occasion</p>
            </div>
            <Link href="/festivals" className="btn btn-outline">All rituals</Link>
          </div>

          {calendarFestivals.length > 0 ? (
            <div className="grid grid-4">
              {calendarFestivals.map((festival) => {
                const days = daysUntil(festival.date);
                const kit = kits.find((k) => k.festival_type === festival.festival_type);
                return (
                  <Link
                    // A festival with no kit must not link to a filter that would
                    // come back empty — send those shoppers to the recommender.
                    href={kit
                      ? `/festivals?type=${festival.festival_type}`
                      : '/recommendations'}
                    key={festival.id}
                    className="card"
                  >
                    <div className={styles.festivalCard}>
                      <div className={styles.festivalDate}>
                        {new Date(`${festival.date}T00:00:00`).toLocaleDateString('en-US', {
                          day: 'numeric', month: 'short',
                        })}
                      </div>
                      <h3>{festival.name}</h3>
                      <p className={styles.festivalWhen}>
                        {countdownLabel(days) || formatFestivalDate(festival.date)}
                      </p>
                      <span className={styles.linkText}>
                        {kit ? 'Get kit' : 'See what you need'} →
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : (
            <div className={loadFailed ? styles.errorState : styles.emptyState}>
              <span aria-hidden="true">{loadFailed ? '⚠️' : '🗓️'}</span>
              <h3>{loadFailed ? 'Festival information is unavailable right now' : 'No upcoming festivals scheduled'}</h3>
              <p>
                {loadFailed
                  ? 'We could not reach the store service. Please refresh in a moment.'
                  : 'Check back soon — we add festival kits ahead of every occasion.'}
              </p>
              <Link href="/festivals" className="btn btn-primary mt-4">Browse all rituals</Link>
            </div>
          )}
        </div>
      </section>

      {/* Shop by ritual — the fourth discovery entry point. A festival arrives on
          a date; a rite of passage happens when a family needs it. */}
      {pujas.length > 0 && (
        <section className="section bg-secondary">
          <div className="container">
            <div className={styles.sectionHeader}>
              <div>
                <h2 className="section-title">Shop by Ritual</h2>
                <p className="section-subtitle">
                  Tell us the ceremony and we will list what it needs
                </p>
              </div>
              <Link href="/pujas" className="btn btn-outline">All rituals</Link>
            </div>

            <div className="grid grid-4">
              {pujas.slice(0, 4).map((puja) => (
                <Link href={`/pujas/${puja.slug}`} key={puja.id} className="card">
                  <div className={styles.ritualCard}>
                    {puja.kit_id && <span className={styles.ritualKitTag}>Kit available</span>}
                    <h3>{puja.name}</h3>
                    <p className={styles.ritualCount}>
                      {puja.required_count} essential item
                      {puja.required_count === 1 ? '' : 's'}
                    </p>
                    <span className={styles.linkText}>See the samagri →</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Featured products */}
      <section className="section">
        <div className="container">
          <div className={styles.sectionHeader}>
            <div>
              <h2 className="section-title">Featured Samagri</h2>
              <p className="section-subtitle">Handpicked essentials for your daily devotion</p>
            </div>
            <Link href="/products" className="btn btn-outline">View shop</Link>
          </div>

          {featuredProducts.length > 0 ? (
            <div className="grid grid-4">
              {featuredProducts.slice(0, 8).map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>
          ) : (
            <div className={loadFailed ? styles.errorState : styles.emptyState}>
              <span aria-hidden="true">{loadFailed ? '⚠️' : '🪔'}</span>
              <h3>{loadFailed ? 'Products are unavailable right now' : 'No featured products yet'}</h3>
              <p>
                {loadFailed
                  ? 'We could not reach the store service. Please refresh in a moment.'
                  : 'Our catalog is being stocked. Browse everything we have so far.'}
              </p>
              <Link href="/products" className="btn btn-primary mt-4">Browse products</Link>
            </div>
          )}
        </div>
      </section>

      {/* Why choose us */}
      <section className="section bg-dark">
        <div className="container">
          <div className="grid grid-2" style={{ alignItems: 'center' }}>
            <div>
              <h2 className="section-title" style={{ color: 'white' }}>Authentic. Pure. <br/><span style={{ color: 'var(--secondary)' }}>Convenient.</span></h2>
              <p className="section-subtitle" style={{ color: 'rgba(255,255,255,0.7)' }}>
                We understand the importance of purity in religious ceremonies. That&apos;s why we source our samagri directly from trusted suppliers and traditional artisans.
              </p>
              <ul className={styles.benefitsList}>
                <li>✅ <strong>Complete Kits:</strong> Don&apos;t run from shop to shop. Get everything in one kit.</li>
                <li>✅ <strong>Required Samagri:</strong> Every kit marks what is essential and what is optional.</li>
                <li>✅ <strong>Smart Recommendations:</strong> Tell us your ritual, we&apos;ll tell you what you need.</li>
                <li>✅ <strong>Kathmandu Focus:</strong> Same-day or next-day delivery within the valley.</li>
              </ul>
              {recMeta && (
                <p className={styles.modelNote}>
                  Recommendations ranked by <strong>{recMeta.algorithm}</strong> over{' '}
                  {recMeta.candidate_count} candidates
                  {recMeta.personalised
                    ? ', personalised from your order history.'
                    : '. Sign in to personalise them with your order history.'}
                </p>
              )}
            </div>
            <div className={styles.mandalaArt}>
              <div className={styles.mandalaCircle1}></div>
              <div className={styles.mandalaCircle2}></div>
              <div className={styles.mandalaIcon}>🕉️</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
