'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCart } from '@/context/CartContext';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { useWishlist } from '@/context/WishlistContext';
import styles from './ProductCard.module.css';

/**
 * One product card, used by the home page, the catalogue and the
 * recommendations page.
 *
 * These were three separate implementations that had quietly diverged: the home
 * version omitted the unit, used a different category class, and its "+" button
 * had no handler at all — it looked like an add-to-cart control and did nothing.
 * Sharing the component means the behaviour and the look cannot drift again.
 *
 * Client component because of the add-to-cart button. It reads the cart context
 * itself rather than taking a callback, so a Server Component (the home page)
 * can render it without passing a function across the boundary.
 *
 * @param {object}  product   A serialized product. `in_stock` drives the button.
 * @param {string}  [reason]  Why this product is here. Rendered verbatim from the
 *                            API — the client never invents a reason. Search passes
 *                            its match reason, recommendations their recommendation.
 * @param {string}  [reasonIcon] Marker for that reason. Defaults to the sparkle the
 *                            recommendations page uses; search passes a magnifier,
 *                            because a search hit is not a recommendation and should
 *                            not be dressed as one.
 * @param {string}  [badge]   Festival-urgency label, e.g. "In 3 days".
 * @param {boolean} [showAdd] Set false for a purely navigational card.
 */
export default function ProductCard({
  product, reason, reasonIcon = '✨', badge, showAdd = true,
}) {
  const { addToCart } = useCart();
  const { user, loading: authLoading } = useAuth();
  const { success, error } = useToast();
  const { isWishlisted, isPending, toggle, wishlistLoaded } = useWishlist();
  const router = useRouter();

  const signedIn = Boolean(user);
  const saved = isWishlisted(product.id);
  const wishBusy = isPending(product.id);

  const handleAddToCart = async (event) => {
    // The whole card is a link, so the click must not also navigate.
    event.preventDefault();
    event.stopPropagation();

    if (!signedIn) {
      // Sending the request would come back 401 and surface "Session expired.
      // Please login again." — nonsense to somebody who was never signed in.
      // Send them to login and bring them back to this product afterwards.
      router.push(`/auth/login?redirect=/products/${product.slug}`);
      return;
    }

    try {
      await addToCart(product.id, 1);
      success(`${product.name} added to cart`);
    } catch (err) {
      error(err.message || 'Could not add to cart');
    }
  };

  const handleWishlist = async (event) => {
    // Same reason as the cart button: this sits inside the card's <Link>.
    event.preventDefault();
    event.stopPropagation();

    if (!signedIn) {
      router.push(`/auth/login?redirect=/products/${product.slug}`);
      return;
    }

    try {
      const nowSaved = await toggle(product);
      success(nowSaved ? `${product.name} saved to your wishlist` : `${product.name} removed from wishlist`);
    } catch (err) {
      error(err.message || 'Could not update your wishlist');
    }
  };

  return (
    <Link href={`/products/${product.slug}`} className="card">
      <div className={styles.productCard}>
        <div className={styles.productImage}>
          {product.image ? (
            /*
              `loading="lazy"` + `decoding="async"` matter more here than they
              look: the home page renders this card ~20 times, and the source
              images were ~700 KB each, so the browser was decoding ~14 MB of
              image data during the first scroll. Lazy defers everything below
              the fold; async decode keeps the decode off the main thread so it
              cannot block a scroll frame. `width`/`height` are deliberately NOT
              set — the CSS gives the wrapper `aspect-ratio: 1`, which already
              reserves the box, so there is no layout shift to guard against.
            */
            <img
              src={product.image}
              alt={product.name}
              loading="lazy"
              decoding="async"
            />
          ) : (
            <div className={styles.placeholderImg} aria-hidden="true">🪔</div>
          )}
          {badge && <span className={styles.urgencyBadge}>{badge}</span>}
          {!product.in_stock && <span className={styles.outOfStock}>Out of Stock</span>}
          {/*
            Hidden until the wishlist has actually loaded. `wishlistLoaded` is a
            *loaded* flag, not a loading flag — see WishlistContext — because a heart
            that renders "not saved" during the fetch would flip a moment later and
            invite the customer to re-save something they already saved.
          */}
          <button
            type="button"
            className={[
              styles.wishBtn,
              saved ? styles.wishBtnSaved : '',
              wishlistLoaded ? '' : styles.wishBtnPending,
            ].filter(Boolean).join(' ')}
            onClick={handleWishlist}
            disabled={!wishlistLoaded || wishBusy || authLoading}
            aria-pressed={wishlistLoaded ? saved : undefined}
            title={signedIn
              ? (saved ? 'Remove from wishlist' : 'Save for later')
              : 'Log in to save this'}
            aria-label={signedIn
              ? (saved ? `Remove ${product.name} from your wishlist` : `Save ${product.name} to your wishlist`)
              : `Log in to save ${product.name}`}
          >
            <span aria-hidden="true">{saved ? '♥' : '♡'}</span>
          </button>
        </div>

        <div className={styles.productInfo}>
          <span className={styles.categoryBadge}>{product.category_name}</span>
          <h4>{product.name}</h4>
          <p className={styles.unitText}>Per {product.unit}</p>

          {reason && (
            <div className={styles.reasonBox}>
              <span className={styles.reasonIcon} aria-hidden="true">{reasonIcon}</span>
              <span className={styles.reasonText}>{reason}</span>
            </div>
          )}

          <div className={styles.productFooter}>
            <span className={styles.price}>Rs. {product.price}</span>
            {showAdd && (
              <button
                className={`btn ${product.in_stock ? 'btn-primary' : 'btn-outline'} btn-icon`}
                onClick={handleAddToCart}
                disabled={!product.in_stock || authLoading}
                title={signedIn ? undefined : 'Log in to add to cart'}
                aria-label={signedIn
                  ? `Add ${product.name} to cart`
                  : `Log in to add ${product.name} to cart`}
              >
                +
              </button>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
