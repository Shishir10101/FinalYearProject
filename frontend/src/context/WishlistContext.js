'use client';
import {
  createContext, useContext, useState, useEffect, useCallback, useMemo,
} from 'react';
import { wishlistAPI } from '@/lib/api';
import { useAuth } from './AuthContext';

const WishlistContext = createContext(null);

/**
 * The signed-in customer's saved products, held once for the whole app.
 *
 * **Why a context rather than a flag on each product payload.** The heart appears on
 * every `ProductCard` — the home page, the catalogue, search results, the
 * recommendations page and the wishlist itself. Asking the server "is this saved?"
 * per card would be one request per card, and putting `is_wishlisted` on
 * `ProductListSerializer` would mean an annotation on every product list in the
 * project for the benefit of one button. Loading the id set once and answering from
 * memory keeps every list query exactly as it was.
 *
 * **`wishlistLoaded` is a loaded flag, not a loading flag** — the same distinction
 * `CartContext.cartLoaded` exists for. `loading` starts `false`, so a heart rendered
 * while the list is still in flight would read "not saved" and then flip to "saved"
 * a moment later: a visible lie, and on a slow connection a customer's own saved
 * item would appear un-saved long enough for them to click it and add a duplicate.
 * The heart renders in a neutral state until this is true.
 */
export function WishlistProvider({ children }) {
  // Product ids, newest save first. A Set would be the natural container, but the
  // order is useful for the wishlist page's optimistic reordering, so the array is
  // kept and membership is answered through a memoised Set.
  const [productIds, setProductIds] = useState([]);
  // `undefined` = nothing loaded yet, `null` = loaded and nobody is signed in,
  // a number = loaded for that user. Mirrors `CartContext.loadedForUserId`.
  const [loadedForUserId, setLoadedForUserId] = useState(undefined);
  // Product ids with a request in flight, so the heart can disable itself and a
  // double-click cannot fire two toggles.
  const [pendingIds, setPendingIds] = useState([]);
  const { user } = useAuth();

  const load = useCallback(async () => {
    if (!user) {
      setProductIds([]);
      setLoadedForUserId(null);
      return;
    }
    try {
      const rows = await wishlistAPI.list();
      setProductIds((rows || []).map((row) => row.product.id));
      setLoadedForUserId(user.id);
    } catch (e) {
      // Deliberately leaves `loadedForUserId` alone: a failed fetch must not look
      // like "you have saved nothing", for the reason in the docstring above.
      console.error('Failed to load wishlist:', e);
    }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const idSet = useMemo(() => new Set(productIds), [productIds]);

  const isWishlisted = useCallback(
    (productId) => idSet.has(productId),
    [idSet],
  );

  const isPending = useCallback(
    (productId) => pendingIds.includes(productId),
    [pendingIds],
  );

  /**
   * Save or unsave, returning the new saved state.
   *
   * The state is updated **after** the request resolves rather than optimistically:
   * the button is disabled while in flight, so there is no window in which a
   * double-click can race, and a failed request then leaves the heart showing the
   * truth instead of a state the server rejected. Throws on failure so the caller
   * can surface a message — this context deliberately owns no toasts, because
   * `ToastContext` is a sibling provider and importing it here would make the two
   * contexts depend on each other.
   */
  const toggle = useCallback(async (product) => {
    const productId = product.id;
    const wasSaved = idSet.has(productId);

    setPendingIds((prev) => [...prev, productId]);
    try {
      if (wasSaved) {
        await wishlistAPI.remove(productId);
        setProductIds((prev) => prev.filter((id) => id !== productId));
        return false;
      }
      await wishlistAPI.add(productId);
      setProductIds((prev) => [productId, ...prev.filter((id) => id !== productId)]);
      return true;
    } finally {
      setPendingIds((prev) => prev.filter((id) => id !== productId));
    }
  }, [idSet]);

  const value = useMemo(() => ({
    productIds,
    wishlistCount: productIds.length,
    // True once the list reflects the signed-in user (or the absence of one).
    wishlistLoaded: loadedForUserId === (user ? user.id : null),
    isWishlisted,
    isPending,
    toggle,
    reload: load,
  }), [productIds, loadedForUserId, user, isWishlisted, isPending, toggle, load]);

  return (
    <WishlistContext.Provider value={value}>
      {children}
    </WishlistContext.Provider>
  );
}

export function useWishlist() {
  const context = useContext(WishlistContext);
  if (!context) throw new Error('useWishlist must be used within WishlistProvider');
  return context;
}
