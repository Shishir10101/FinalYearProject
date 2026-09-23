'use client';
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { cartAPI, ordersAPI } from '@/lib/api';
import { useAuth } from './AuthContext';

const CartContext = createContext(null);

export function CartProvider({ children }) {
  const [cartItems, setCartItems] = useState([]);
  const [cartSubtotal, setCartSubtotal] = useState(0);
  const [cartTotal, setCartTotal] = useState(0);
  const [cartCount, setCartCount] = useState(0);
  const [deliveryFee, setDeliveryFee] = useState(0);
  const [loading, setLoading] = useState(false);
  // Which user the current cart state belongs to. `undefined` = nothing loaded yet,
  // `null` = loaded and nobody is signed in, a number = loaded for that user.
  //
  // This exists because `loading` starts `false`, so a guard like
  // `!loading && cartItems.length === 0` cannot tell "the cart is empty" from "the
  // cart has not been fetched yet". `/checkout` did exactly that and **bounced a
  // full page load of /checkout to /cart even with a full cart** — refresh, a
  // bookmark and a shared link all broke. The happy path hid it: navigating from
  // the cart is a client-side route change, so this provider never remounts and the
  // items are already in state.
  const [loadedForUserId, setLoadedForUserId] = useState(undefined);
  const { user } = useAuth();

  // Delivery fee is owned by the backend so the cart, the checkout button and the
  // saved order can never disagree. See GET /api/orders/config/.
  useEffect(() => {
    let cancelled = false;
    ordersAPI.config
      ? ordersAPI.config()
          .then(cfg => { if (!cancelled) setDeliveryFee(cfg.delivery_fee ?? 0); })
          .catch(() => {})
      : null;
    return () => { cancelled = true; };
  }, []);

  const loadCart = useCallback(async () => {
    if (!user) {
      setCartItems([]);
      setCartSubtotal(0);
      setCartTotal(0);
      setCartCount(0);
      setLoadedForUserId(null);
      return;
    }
    try {
      setLoading(true);
      const data = await cartAPI.get();
      setCartItems(data.items || []);
      setCartSubtotal(data.subtotal ?? 0);
      setCartTotal(data.total || 0);
      setCartCount(data.count || 0);
      if (data.delivery_fee !== undefined) setDeliveryFee(data.delivery_fee);
      setLoadedForUserId(user.id);
    } catch (e) {
      // Deliberately leaves `loadedForUserId` untouched. A failed fetch must not
      // look like an empty cart, or the checkout page would bounce the customer for
      // a backend blip — the very bug this flag exists to prevent.
      console.error('Failed to load cart:', e);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    loadCart();
  }, [loadCart]);

  const addToCart = async (productId, quantity = 1) => {
    await cartAPI.add(productId, quantity);
    await loadCart();
  };

  const updateQuantity = async (cartItemId, quantity) => {
    await cartAPI.update(cartItemId, quantity);
    await loadCart();
  };

  const removeFromCart = async (cartItemId) => {
    await cartAPI.remove(cartItemId);
    await loadCart();
  };

  const addKitToCart = async (kitId) => {
    await cartAPI.addKit(kitId);
    await loadCart();
  };

  const clearCartState = () => {
    setCartItems([]);
    setCartSubtotal(0);
    setCartTotal(0);
    setCartCount(0);
  };

  return (
    <CartContext.Provider value={{
      cartItems, cartSubtotal, cartTotal, cartCount, deliveryFee, loading,
      // True once the cart state reflects the signed-in user (or the absence of
      // one). Any page that must not act on a cart it has not fetched yet should
      // wait for this rather than inferring it from `loading`.
      cartLoaded: loadedForUserId === (user ? user.id : null),
      addToCart, updateQuantity, removeFromCart, addKitToCart,
      loadCart, clearCartState
    }}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const context = useContext(CartContext);
  if (!context) throw new Error('useCart must be used within CartProvider');
  return context;
}
