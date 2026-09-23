import Link from 'next/link';

/**
 * Global 404.
 *
 * `PujaDetailPage` calls `notFound()` for an unknown ritual slug. The API itself
 * answers a real HTTP 404 for that slug; the *page* cannot, and the honest reason
 * is Next's streaming model.
 *
 * `src/app/pujas/loading.js` opens a Suspense boundary, so the response has already
 * begun streaming by the time the Server Component's fetch resolves. `notFound()`
 * then renders this UI into an already-committed 200. Measured, not assumed:
 * `curl -o /dev/null -w '%{http_code}' /pujas/<unknown>` returns **200**.
 *
 * This is a known Next constraint, not a bug to be fixed by removing `loading.js` —
 * the skeleton is what makes the ritual pages feel fast. Next injects
 * `<meta name="robots" content="noindex">` as the mitigation, so an unknown slug is
 * still not indexed. See `node_modules/next/dist/docs/01-app/02-guides/streaming.md`.
 *
 * The default Next page is unstyled and looks foreign next to the rest of the store,
 * so this replaces it for every route in the app.
 */
export default function NotFound() {
  return (
    <div className="container section">
      <div
        style={{
          background: 'white',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          padding: 'var(--space-3xl)',
          textAlign: 'center',
          maxWidth: '620px',
          margin: '0 auto',
        }}
      >
        <span style={{ fontSize: '3.5rem', display: 'block', marginBottom: '16px' }} aria-hidden="true">
          🔍
        </span>
        <h1 style={{ fontSize: '1.8rem', color: 'var(--text-primary)', marginBottom: '10px' }}>
          We could not find that page
        </h1>
        <p style={{ color: 'var(--text-muted)', marginBottom: '24px' }}>
          The link may be out of date, or the item may have been removed.
        </p>
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link href="/" className="btn btn-primary">Back to home</Link>
          <Link href="/products" className="btn btn-outline">Browse products</Link>
          <Link href="/pujas" className="btn btn-outline">Shop by ritual</Link>
        </div>
      </div>
    </div>
  );
}
