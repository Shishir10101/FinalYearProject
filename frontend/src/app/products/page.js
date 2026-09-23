'use client';
import { Suspense, useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import { productsAPI } from '@/lib/api';
import { useToast } from '@/context/ToastContext';
import ProductCard from '@/components/ProductCard';
import styles from './products.module.css';

/**
 * The catalogue, and the **Samagri** discovery entry point.
 *
 * `AGENTS.md` §1 requires discovery through six paths and Samagri is one of them.
 * That path used to be `?search=` on this page: a plain substring match that found
 * nothing for a second spelling of a Nepali term, and could not reach the samagri
 * behind a ritual or festival name at all. It now goes through
 * `/api/products/search/`, which ranks by relevance and explains every result.
 *
 * Three deliberate differences from the plain catalogue list:
 *
 * * **Sorting is hidden while a query is active.** Relevance *is* the sort; offering
 *   "Price: Low to High" on top of a ranked result set would silently discard the
 *   ranking and pretend it had not.
 * * **The page reports what it understood** — the alternative spellings it tried and
 *   the rituals it recognised — instead of leaving the shopper to guess why a
 *   product they never named is on screen.
 * * **An empty result set is three different messages.** "Keep typing", "did you
 *   mean", and "nothing matched" are not the same thing, and the API distinguishes
 *   them (`too_short`, `suggestions`) so the UI does not have to guess.
 */

const SORTS = [
  ['-popularity_score', 'Most Popular'],
  ['price', 'Price: Low to High'],
  ['-price', 'Price: High to Low'],
  ['-created_at', 'Newest Arrivals'],
  ['name', 'Name: A to Z'],
];

function CatalogueBrowser() {
  const searchParams = useSearchParams();

  // Read once, lazily. Subscribing to `searchParams` would re-sync on every URL
  // update below and fight the user's typing.
  const [searchInput, setSearchInput] = useState(() => searchParams.get('q') || '');
  const [activeQuery, setActiveQuery] = useState(() => searchParams.get('q') || '');

  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [activeCategory, setActiveCategory] = useState('');
  const [sortBy, setSortBy] = useState('-popularity_score');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [meta, setMeta] = useState(null);

  const { error } = useToast();

  const searching = Boolean(activeQuery);

  useEffect(() => {
    productsAPI.categories().then(setCategories).catch((e) => console.error(e));
  }, []);

  const load = useCallback(async (nextPage = 1, append = false) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      let data;
      if (activeQuery) {
        data = await productsAPI.search({
          q: activeQuery,
          category: activeCategory,
          page: nextPage,
        });
      } else {
        const params = new URLSearchParams();
        if (activeCategory) params.append('category', activeCategory);
        if (sortBy) params.append('ordering', sortBy);
        params.append('page', String(nextPage));
        data = await productsAPI.list(params.toString());
      }

      const rows = data.results || data || [];
      setProducts((prev) => (append ? [...prev, ...rows] : rows));
      setTotal(typeof data.count === 'number' ? data.count : rows.length);
      setMeta(activeQuery ? data : null);
      setPage(nextPage);
    } catch (e) {
      console.error(e);
      error(activeQuery ? 'Could not run that search' : 'Failed to load products');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [activeQuery, activeCategory, sortBy, error]);

  useEffect(() => { load(1, false); }, [load]);

  /**
   * Keep the URL shareable — a search that cannot be linked to cannot be shared,
   * bookmarked or demonstrated.
   *
   * `window.history.replaceState` rather than `router.replace`, and that is not a
   * style preference. Measured: on this statically prerendered route, replacing a
   * query that was *already in the URL* with a different value did nothing at all —
   * no RSC request, and the address bar still read `?q=sindoer` while the page
   * showed results for "sindoor". Going from no query to a query worked, which is
   * what made it look fine at first. `replaceState` is the documented way to update
   * search params from a Client Component and the App Router keeps `useSearchParams`
   * in step with it.
   *
   * `replace`, not `push`: the back button should not walk back through every query
   * the shopper tried.
   */
  const syncUrl = (query) => {
    if (typeof window === 'undefined') return;
    window.history.replaceState(
      null, '', query ? `/products?q=${encodeURIComponent(query)}` : '/products',
    );
  };

  const submitSearch = (event) => {
    event.preventDefault();
    const query = searchInput.trim();
    setActiveQuery(query);
    syncUrl(query);
  };

  const clearAll = () => {
    setSearchInput('');
    setActiveQuery('');
    setActiveCategory('');
    setSortBy('-popularity_score');
    syncUrl('');
  };

  // Not named `useSuggestion`: a `use`-prefixed name makes ESLint treat it as a
  // React hook, and calling it from inside a click handler is then an error.
  const applySuggestion = (term) => {
    setSearchInput(term);
    setActiveQuery(term);
    syncUrl(term);
  };

  const shown = products.length;
  const hasMore = shown < total;

  // The spellings the API tried beyond what was typed. Shown as a quiet line, not a
  // headline: the per-card reason already explains the match, and this is the reason
  // the *query* found anything at all.
  const alsoTried = (meta?.expanded_terms || []).filter(
    (term) => !(meta?.tokens || []).includes(term),
  );

  return (
    <div className="container section">
      <div className={styles.header}>
        <div>
          <h1 className="section-title">
            {searching ? <>Results for &ldquo;{activeQuery}&rdquo;</> : 'All Products'}
          </h1>
          {/* Announced politely when a search resolves: the result count changes
              without a page navigation, so a screen reader would otherwise never
              learn that anything happened. */}
          <p
            className="section-subtitle"
            role={searching ? 'status' : undefined}
            aria-live={searching ? 'polite' : undefined}
          >
            {searching
              ? `${total} ${total === 1 ? 'product' : 'products'} found, best match first`
              : 'Browse our complete collection of authentic puja samagri'}
          </p>
        </div>
      </div>

      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <div className={styles.filterGroup}>
            <form onSubmit={submitSearch} className={styles.searchBox}>
              <input
                type="text"
                placeholder="Search samagri..."
                className="form-input"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                aria-label="Search samagri"
              />
              <button type="submit" className={styles.searchBtn} aria-label="Search">🔍</button>
            </form>
          </div>

          {/* Relevance is the sort while a query is active, so the control is
              removed rather than left to look broken. */}
          {!searching && (
            <div className={styles.filterGroup}>
              <h3 className={styles.filterTitle}>Sort By</h3>
              <select
                className="form-select"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                aria-label="Sort products"
              >
                {SORTS.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
          )}

          <div className={styles.filterGroup}>
            <h3 className={styles.filterTitle}>Categories</h3>
            <ul className={styles.categoryList}>
              <li>
                <button
                  className={`${styles.catBtn} ${activeCategory === '' ? styles.catActive : ''}`}
                  onClick={() => setActiveCategory('')}
                >
                  All Products
                </button>
              </li>
              {categories.map((cat) => (
                <li key={cat.id}>
                  <button
                    className={`${styles.catBtn} ${activeCategory === cat.id ? styles.catActive : ''}`}
                    onClick={() => setActiveCategory(cat.id)}
                  >
                    {cat.name} <span className={styles.catCount}>({cat.product_count})</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </aside>

        {/* A `<div>`, not a `<main>`: the layout already provides the page's single
            main landmark, and a second one nested inside it is both invalid HTML and
            ambiguous for a screen reader — "go to main content" stops having one
            answer. */}
        <div className={styles.mainContent}>
          {searching && !loading && (
            <div className={styles.searchInsight}>
              {(meta?.matched_domains || []).length > 0 && (
                <p className={styles.insightLine}>
                  <span aria-hidden="true">🪔</span>{' '}
                  Showing samagri for{' '}
                  {(meta.matched_domains || []).map((entry, index) => (
                    <span key={`${entry.kind}-${entry.ref}`}>
                      {index > 0 && ', '}
                      <strong>{entry.name}</strong>{' '}
                      <span className={styles.insightKind}>({entry.kind})</span>
                    </span>
                  ))}
                </p>
              )}
              {alsoTried.length > 0 && (
                <p className={styles.insightLine}>
                  <span aria-hidden="true">🔤</span>{' '}
                  Also searched for {alsoTried.slice(0, 4).join(', ')}
                </p>
              )}
            </div>
          )}

          {loading ? (
            <div className="grid grid-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="card skeleton" style={{ height: '350px' }} />
              ))}
            </div>
          ) : products.length === 0 ? (
            <div className={styles.emptyState}>
              <span className={styles.emptyIcon}>{meta?.too_short ? '⌨️' : '🔍'}</span>
              {meta?.too_short ? (
                <>
                  <h3>Keep typing</h3>
                  <p>Type at least two characters and we will search the catalogue.</p>
                </>
              ) : searching && (meta?.suggestions || []).length > 0 ? (
                <>
                  <h3>Nothing matches &ldquo;{activeQuery}&rdquo;</h3>
                  <p>Did you mean one of these?</p>
                  <div className={styles.suggestionRow}>
                    {(meta.suggestions || []).map((term) => (
                      <button
                        key={term}
                        className="btn btn-outline"
                        onClick={() => applySuggestion(term)}
                      >
                        {term}
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <>
                  <h3>No products found</h3>
                  <p>
                    {searching
                      ? `Nothing in the catalogue matches “${activeQuery}”.`
                      : 'Try adjusting your filters to find what you are looking for.'}
                  </p>
                  <button className="btn btn-outline mt-4" onClick={clearAll}>
                    Clear Filters
                  </button>
                </>
              )}
            </div>
          ) : (
            <>
              <div className="grid grid-3">
                {products.map((product) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    // Straight from the API's `match` block — the first reason is the
                    // strongest one. The client never invents this.
                    reason={product.match?.reasons?.[0]}
                    reasonIcon="🔍"
                  />
                ))}
              </div>

              {hasMore && (
                <div className={styles.moreRow}>
                  <button
                    className="btn btn-outline"
                    onClick={() => load(page + 1, true)}
                    disabled={loadingMore}
                  >
                    {loadingMore ? 'Loading…' : `Show more (${total - shown} left)`}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ProductsPage() {
  // `useSearchParams()` must sit inside a <Suspense> boundary or the production
  // build fails. See the Next.js 16 note in AGENTS.md §2.
  return (
    <Suspense fallback={
      <div className="container section">
        <div className="skeleton-block" style={{ height: '420px' }} />
      </div>
    }>
      <CatalogueBrowser />
    </Suspense>
  );
}
