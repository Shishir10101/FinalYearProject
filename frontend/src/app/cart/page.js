'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCart } from '@/context/CartContext';
import { useToast } from '@/context/ToastContext';
import styles from './cart.module.css';

export default function CartPage() {
  const { cartItems, cartSubtotal, cartTotal, deliveryFee, loading, updateQuantity, removeFromCart, loadCart, cartLoaded } = useCart();
  const { success, error } = useToast();
  const router = useRouter();
  const [updating, setUpdating] = useState(false);

  // Force a load when landing on cart page
  useEffect(() => {
    loadCart();
  }, [loadCart]);

  const handleUpdate = async (id, newQuantity) => {
    if (newQuantity < 1) return;
    setUpdating(true);
    try {
      await updateQuantity(id, newQuantity);
    } catch (e) {
      error(e.message || "Failed to update quantity");
    } finally {
      setUpdating(false);
    }
  };

  const handleRemove = async (id) => {
    if (window.confirm('Remove this item from cart?')) {
      setUpdating(true);
      try {
        await removeFromCart(id);
        success("Item removed");
      } catch (e) {
        error("Failed to remove item");
      } finally {
        setUpdating(false);
      }
    }
  };

  // `cartLoaded` rather than `loading`: on a fresh page load the cart is empty and
  // `loading` is still false, so this used to tell a customer with a full cart that
  // their cart was empty — briefly, but it is the wrong thing to say either way.
  if (!cartLoaded || (loading && cartItems.length === 0)) {
    return <div className="container section text-center">Loading cart...</div>;
  }

  if (cartItems.length === 0) {
    return (
      <div className="container section">
        <div className={styles.emptyCart}>
          <div className={styles.emptyIcon}>🛒</div>
          <h2>Your cart is empty</h2>
          <p>Looks like you haven&apos;t added any samagri to your cart yet.</p>
          <div className="mt-4 flex gap-4 justify-center">
            <Link href="/products" className="btn btn-primary">Browse Products</Link>
            <Link href="/festivals" className="btn btn-outline">View Festival Kits</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container section">
      <h1 className="section-title mb-4">Your Shopping Cart</h1>
      
      <div className={styles.layout}>
        {/* Cart Items */}
        <div className={styles.itemsColumn}>
          <div className={styles.cartCard}>
            <div className={styles.cartHeader}>
              <div className={styles.colProduct}>Product</div>
              <div className={styles.colPrice}>Price</div>
              <div className={styles.colQuantity}>Quantity</div>
              <div className={styles.colTotal}>Total</div>
              <div className={styles.colAction}></div>
            </div>
            
            <ul className={styles.itemList}>
              {cartItems.map((item) => (
                <li key={item.id} className={styles.itemRow}>
                  <div className={styles.colProduct}>
                    <div className={styles.itemImage}>
                      {item.product_detail.image ? (
                        <img src={item.product_detail.image} alt={item.product_detail.name} />
                      ) : (
                        <span>🪔</span>
                      )}
                    </div>
                    <div className={styles.itemInfo}>
                      <Link href={`/products/${item.product_detail.slug}`} className={styles.itemName}>
                        {item.product_detail.name}
                      </Link>
                      <span className={styles.itemCategory}>{item.product_detail.category_name}</span>
                    </div>
                  </div>
                  
                  <div className={styles.colPrice}>
                    Rs. {item.product_detail.price}
                  </div>
                  
                  <div className={styles.colQuantity}>
                    <div className={styles.quantityControl}>
                      <button 
                        onClick={() => handleUpdate(item.id, item.quantity - 1)}
                        disabled={item.quantity <= 1 || updating}
                      >-</button>
                      <span>{item.quantity}</span>
                      <button 
                        onClick={() => handleUpdate(item.id, item.quantity + 1)}
                        disabled={item.quantity >= item.product_detail.stock || updating}
                      >+</button>
                    </div>
                  </div>
                  
                  <div className={styles.colTotal}>
                    Rs. {item.subtotal}
                  </div>
                  
                  <div className={styles.colAction}>
                    <button 
                      className={styles.removeBtn}
                      onClick={() => handleRemove(item.id)}
                      disabled={updating}
                      title="Remove Item"
                    >
                      🗑️
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Order Summary */}
        <div className={styles.summaryColumn}>
          <div className={styles.summaryCard}>
            <h3>Order Summary</h3>
            
            <div className={styles.summaryRow}>
              <span>Subtotal ({cartItems.length} items)</span>
              <span>Rs. {cartSubtotal}</span>
            </div>
            
            <div className={styles.summaryRow}>
              <span>Delivery Charge</span>
              <span>Rs. {deliveryFee}</span>
            </div>
            
            <div className={styles.summaryDivider}></div>
            
            <div className={styles.summaryRowTotal}>
              <span>Total Amount</span>
              <span>Rs. {cartTotal}</span>
            </div>
            
            <Link href="/checkout" className="btn btn-primary btn-lg" style={{width: '100%', marginTop: '20px'}}>
              Proceed to Checkout
            </Link>
            
            <div className={styles.secureText}>
              🔒 Secure checkout processing
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
