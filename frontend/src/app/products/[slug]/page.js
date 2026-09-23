'use client';
import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { productsAPI } from '@/lib/api';
import { useCart } from '@/context/CartContext';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { useWishlist } from '@/context/WishlistContext';
import ReviewsSection from '@/components/ReviewsSection';
import styles from './detail.module.css';

export default function ProductDetailPage() {
  const params = useParams();
  const slug = params.slug;
  
  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [quantity, setQuantity] = useState(1);
  const [relatedProducts, setRelatedProducts] = useState([]);
  // Held separately from `product` so a review write can update the header stars
  // without refetching the whole product.
  const [rating, setRating] = useState({ average: null, count: 0 });
  
  const { addToCart } = useCart();
  const { success, error } = useToast();
  const { user } = useAuth();
  const { isWishlisted, isPending, toggle, wishlistLoaded } = useWishlist();
  const router = useRouter();

  useEffect(() => {
    fetchProductDetail();
  }, [slug]);

  const fetchProductDetail = async () => {
    try {
      const data = await productsAPI.detail(slug);
      setProduct(data);
      setRating({
        average: data.average_rating ?? null,
        count: data.review_count ?? 0,
      });
      
      // Fetch related products from same category
      if (data.category && data.category.slug) {
        const related = await productsAPI.byCategory(data.category.slug);
        const filtered = (related.results || related).filter(p => p.id !== data.id).slice(0, 4);
        setRelatedProducts(filtered);
      }
    } catch (e) {
      console.error(e);
      error("Product not found");
    } finally {
      setLoading(false);
    }
  };

  /**
   * Stable, and it bails out when the numbers have not actually moved.
   *
   * `ReviewsSection` calls this after every load, including the first one on mount —
   * and its `load` is the dependency of its own mount effect. An inline arrow here is
   * a new function on every render, which is what turned into a fetch loop before the
   * section started holding it in a ref. Keeping it stable means the section cannot
   * loop even if that guard is ever removed, and returning the previous object when
   * the values are unchanged stops this page re-rendering for nothing.
   */
  const handleSummaryChange = useCallback((average, count) => {
    setRating((prev) => (
      prev.average === average && prev.count === count ? prev : { average, count }
    ));
  }, []);

  const handleAddToCart = async () => {
    try {
      await addToCart(product.id, quantity);
      success(`${quantity} ${product.name} added to cart`);
    } catch (e) {
      error(e.message || "Failed to add to cart");
    }
  };

  /**
   * Save or unsave this product.
   *
   * `product.is_wishlisted` comes down with the detail payload, so the button is
   * correct on first paint — but membership is read from the context, not from that
   * field, because the context is what the heart on every *card* uses. Reading the
   * same source in both places is what stops this page and the catalogue from
   * disagreeing after a toggle.
   */
  const handleToggleWishlist = async () => {
    if (!user) {
      router.push(`/auth/login?redirect=/products/${product.slug}`);
      return;
    }
    try {
      const nowSaved = await toggle(product);
      success(nowSaved
        ? `${product.name} saved to your wishlist`
        : `${product.name} removed from wishlist`);
    } catch (e) {
      error(e.message || 'Could not update your wishlist');
    }
  };

  if (loading) {
    return <div className="container section">Loading...</div>;
  }

  if (!product) {
    return (
      <div className="container section text-center">
        <h2>Product not found</h2>
        <Link href="/products" className="btn btn-primary mt-4">Back to Products</Link>
      </div>
    );
  }

  return (
    <div className="container section">
      {/* Breadcrumb */}
      <div className={styles.breadcrumb}>
        <Link href="/">Home</Link> &gt; 
        <Link href="/products">Products</Link> &gt; 
        <Link href={`/products?category=${product.category.id}`}>{product.category.name}</Link> &gt; 
        <span>{product.name}</span>
      </div>

      <div className={styles.productContainer}>
        {/* Image Gallery */}
        <div className={styles.imageGrid}>
          <div className={styles.mainImage}>
             {product.image ? (
                <img src={product.image} alt={product.name} />
              ) : (
                <div className={styles.placeholderImg}>🪔</div>
              )}
          </div>
        </div>

        {/* Product Details */}
        <div className={styles.details}>
          <div className="badge badge-secondary mb-2">{product.category.name}</div>
          <h1 className={styles.title}>{product.name}</h1>

          {/*
            The rating sits with the title because it is what a shopper looks for
            first. It links down to the reviews rather than repeating them, and it
            says "No reviews yet" rather than showing an empty five-star row — an
            unrated product has no rating, and rendering that as zero stars would be
            a claim the data does not support.
          */}
          <a href="#reviews" className={styles.ratingLine}>
            {rating.count > 0 ? (
              <>
                <span className={styles.ratingStars} aria-hidden="true">
                  {'★'.repeat(Math.round(rating.average || 0))}
                  <span className={styles.ratingStarsOff}>
                    {'★'.repeat(5 - Math.round(rating.average || 0))}
                  </span>
                </span>
                <span className={styles.ratingValue}>{rating.average.toFixed(1)}</span>
                <span className={styles.ratingCount}>
                  ({rating.count} review{rating.count === 1 ? '' : 's'})
                </span>
              </>
            ) : (
              <span className={styles.ratingCount}>No reviews yet — write the first</span>
            )}
          </a>
          
          <div className={styles.priceRow}>
            <span className={styles.price}>Rs. {product.price}</span>
            <span className={styles.unit}>per {product.unit}</span>
          </div>
          
          <div className={styles.statusRow}>
            {product.in_stock ? (
              <span className="badge badge-success">✓ In Stock ({product.stock} available)</span>
            ) : (
              <span className="badge badge-danger">✗ Out of Stock</span>
            )}
            
            {product.popularity_score > 50 && (
              <span className="badge badge-warning">🔥 High Demand</span>
            )}
          </div>

          <p className={styles.description}>{product.description}</p>

          <div className={styles.actions}>
            <div className={styles.quantityPicker}>
              <button 
                onClick={() => setQuantity(Math.max(1, quantity - 1))}
                disabled={quantity <= 1}
              >-</button>
              <input 
                type="number" 
                value={quantity} 
                readOnly
              />
              <button 
                onClick={() => setQuantity(Math.min(product.stock, quantity + 1))}
                disabled={quantity >= product.stock}
              >+</button>
            </div>
            
            <button 
              className={`btn btn-primary btn-lg ${styles.addBtn}`}
              onClick={handleAddToCart}
              disabled={!product.in_stock}
            >
              🛒 Add to Cart
            </button>

            {/* Hidden until the wishlist has loaded, for the same reason as the heart
                on the card: showing the un-saved state during the fetch would tell a
                customer their saved item is not saved. */}
            <button
              type="button"
              className={`btn btn-outline btn-lg ${styles.wishBtn}`}
              onClick={handleToggleWishlist}
              disabled={!wishlistLoaded || isPending(product.id)}
              aria-pressed={wishlistLoaded ? isWishlisted(product.id) : undefined}
              style={wishlistLoaded ? undefined : { visibility: 'hidden' }}
            >
              {isWishlisted(product.id) ? '♥ Saved' : '♡ Save for later'}
            </button>
          </div>
          
          <div className={styles.features}>
            <div className={styles.feature}>
              <span>🚚</span> Fast Delivery in Valley
            </div>
            <div className={styles.feature}>
              <span>🕉️</span> 100% Authentic Quality
            </div>
            <div className={styles.feature}>
              <span>💳</span> Secure Payments (eSewa/Khalti)
            </div>
          </div>
        </div>
      </div>

      <ReviewsSection
        slug={slug}
        initialAverage={product.average_rating ?? null}
        initialCount={product.review_count ?? 0}
        onSummaryChange={handleSummaryChange}
      />

      {relatedProducts.length > 0 && (
        <div className={styles.relatedSection}>
          <h2 className="section-title">Similar Items</h2>
          <div className="grid grid-4 mt-4">
             {relatedProducts.map(p => (
                <Link href={`/products/${p.slug}`} key={p.id} className="card p-3">
                  <div style={{aspectRatio: '1', background: '#f5f5f5', borderRadius: '8px', marginBottom: '10px'}}>
                     {p.image && <img src={p.image} alt={p.name} style={{width:'100%', height:'100%', objectFit:'cover', borderRadius:'8px'}} />}
                  </div>
                  <h4 style={{fontSize:'1rem'}}>{p.name}</h4>
                  <p style={{color:'var(--primary)', fontWeight:'bold'}}>Rs. {p.price}</p>
                </Link>
             ))}
          </div>
        </div>
      )}
    </div>
  );
}
