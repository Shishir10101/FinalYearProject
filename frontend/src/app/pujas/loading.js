/**
 * Loading state for the ritual pages.
 *
 * The pages are Server Components, so there is no client-side `loading` flag to
 * flip — this is how Next renders the loading state while the server works. It
 * keeps the four-state rule (loading · success · empty · error) intact without a
 * client boundary.
 */
export default function LoadingPujas() {
  return (
    <div className="container section">
      <div className="skeleton-block" style={{ height: '22px', width: '140px', marginBottom: '16px' }} />
      <div className="skeleton-block" style={{ height: '42px', width: '320px', marginBottom: '12px' }} />
      <div className="skeleton-block" style={{ height: '18px', width: '460px', marginBottom: '36px' }} />

      <div className="grid grid-3">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="card skeleton" style={{ height: '210px' }} />
        ))}
      </div>
    </div>
  );
}
