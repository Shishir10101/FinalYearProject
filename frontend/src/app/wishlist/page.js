'use client';
import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { useWishlist } from '@/context/WishlistContext';
import { wishlistAPI } from '@/lib/api';
import ProductCard from '@/components/ProductCard';

/**
 * Saved products.
 *
 * The storefront's half of the wishlist. `docs/FEATURES.md` listed this as ❌ not
 * built; the backend now exists, and a list you can only add to and never look at
 * would be worse than no list at all.
 *
 * **Why this fetches its own rows instead of reading them from the context.**
 * `WishlistContext` holds only the *product ids*, because that is all the heart on a
 * card needs and holding the full products there would mean one big payload on every
 * page in the app. This page needs the products themselves, so it asks for them —
 * once, on mount.
 *
 * The context still owns membership: removal goes through `toggle()` rather than
 * calling the API directly, so the hearts on this page and on the catalogue cannot
 * end up disagreeing about what is saved.
 */
export default function WishlistPage() {
  const { user, loading: authLoading } = useAuth();
  const { success, error: toastError } = useToast();
  const { toggle, reload } = useWishlist();

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [removingId, setRemovingId] = useState(null);

  const fetchWishlist = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      // A bare array, not `{ results: [...] }` — see the note in lib/api.js.
      const data = await wishlistAPI.list();
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      // Never render a backend failure as "your wishlist is empty" — that tells the
      // customer their saved items are gone.
      setError(e.message || 'Could not load your wishlist.');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setLoading(false);
      return;
    }
    fetchWishlist();
  }, [user, authLoading, fetchWishlist]);

  const handleRemove = async (product) => {
    setRemovingId(product.id);
    try {
      await toggle(product);
      // The row is only dropped once the server has agreed — the button is disabled
      // while this is in flight, so there is no double-click to race.
      setRows((prev) => prev.filter((row) => row.product.id !== product.id));
      success(`${product.name} removed from your wishlist`);
    } catch (e) {
      toastError(e.message || 'Could not remove that item');
    } finally {
      setRemovingId(null);
    }
  };

  if (authLoading || (loading && !error && rows.length === 0 && user)) {
    return (
      <div className="container section">
        <h1 className="section-title">My Wishlist</h1>
        <div className="grid grid-3" style={{ marginTop: '20px' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton-block" style={{ height: '320px', borderRadius: 'var(--radius-md)' }} />
          ))}
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="container section">
        <h1 className="section-title">My Wishlist</h1>
        <div className="empty-state">
          <div className="empty-state-icon">♡</div>
          <h3 className="empty-state-title">Please log in</h3>
          <p className="empty-state-text">
            Your saved samagri lives on your account, so it is still here next visit.
          </p>
          <Link
            href="/auth/login?redirect=/wishlist"
            className="btn btn-primary"
            style={{ marginTop: '16px', display: 'inline-block' }}
          >
            Log in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '12px', flexWrap: 'wrap' }}>
        <h1 className="section-title">My Wishlist</h1>
        {rows.length > 0 && (
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            {rows.length} saved item{rows.length === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {error ? (
        <div className="empty-state" style={{ marginTop: '20px' }}>
          <div className="empty-state-icon">⚠️</div>
          <h3 className="empty-state-title">Could not load your wishlist</h3>
          <p className="empty-state-text">{error}</p>
          <button
            className="btn btn-primary"
            style={{ marginTop: '16px' }}
            onClick={() => { reload(); fetchWishlist(); }}
          >
            Try again
          </button>
        </div>
      ) : rows.length === 0 ? (
        <div className="empty-state" style={{ marginTop: '20px' }}>
          <div className="empty-state-icon">♡</div>
          <h3 className="empty-state-title">Nothing saved yet</h3>
          <p className="empty-state-text">
            Tap the heart on any product to keep it here while you put your puja together.
          </p>
          <Link href="/products" className="btn btn-primary" style={{ marginTop: '16px', display: 'inline-block' }}>
            Browse samagri
          </Link>
        </div>
      ) : (
        <div className="grid grid-3" style={{ marginTop: '20px' }}>
          {rows.map((row) => (
            <div key={row.id} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {/* The card's own heart unsaves via the shared context; this button
                  says so explicitly, because "remove" is the reason a customer
                  comes to this page. */}
              <ProductCard product={row.product} />
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => handleRemove(row.product)}
                disabled={removingId === row.product.id}
              >
                {removingId === row.product.id ? 'Removing…' : 'Remove from wishlist'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
