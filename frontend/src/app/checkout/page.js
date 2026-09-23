'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { useCart } from '@/context/CartContext';
import { useToast } from '@/context/ToastContext';
import { ordersAPI, productsAPI } from '@/lib/api';

export default function CheckoutPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { cartItems, cartSubtotal, cartTotal, deliveryFee, loading: cartLoading, loadCart, cartLoaded } = useCart();
  const { success, error } = useToast();

  const [loading, setLoading] = useState(false);
  // Set the moment an order is accepted. The cart is empty from that point on, so
  // without this the redirect below fires on `cartItems.length === 0` and races the
  // push to the confirmation — the customer's order was placed and they were sent to
  // an empty cart instead, which reads as "it didn't work". Observed in a browser,
  // not by any API test: the order really was created.
  const [placed, setPlaced] = useState(false);
  const [areas, setAreas] = useState([]);
  const [areasError, setAreasError] = useState('');
  // Which payment methods are real, and which are simulated. Served by the API rather
  // than hardcoded here so the label cannot drift from the server's behaviour — the
  // whole point is that the customer is told the truth before choosing.
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [paymentMocked, setPaymentMocked] = useState(false);
  const [formData, setFormData] = useState({
    shipping_address: '',
    shipping_city: '',
    phone: '',
    payment_method: 'cod',
    notes: ''
  });

  // Store configuration: the payment methods and their honesty flags.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await ordersAPI.config();
        if (cancelled) return;
        const methods = cfg?.payment_methods || [];
        setPaymentMethods(methods);
        setPaymentMocked(Boolean(cfg?.any_payment_mocked));
      } catch {
        // Non-fatal. The three methods are still offered below from defaults; the
        // sidebar simply omits the demo notice rather than blocking the purchase.
        // Deliberately silent: this is a disclosure, not a checkout precondition.
        if (!cancelled) setPaymentMethods([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Delivery areas are fetched, not hardcoded. An area added in the admin
  // dashboard must be selectable here without a frontend deploy.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await productsAPI.areas();
        const list = (data.results || data || []).filter((a) => a.is_active !== false);
        if (cancelled) return;
        setAreas(list);
        // Default to the first available area so the form is never unsubmittable.
        setFormData((prev) => (prev.shipping_city ? prev : { ...prev, shipping_city: list[0]?.slug || '' }));
      } catch (e) {
        if (!cancelled) setAreasError(e.message || 'Could not load delivery areas.');
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Prefill from the profile once the user is known.
  useEffect(() => {
    if (!user) return;
    setFormData(prev => ({
      ...prev,
      shipping_address: user.profile?.address || prev.shipping_address,
      shipping_city: user.profile?.city || prev.shipping_city,
      phone: user.profile?.phone || prev.phone,
    }));
  }, [user]);

  // Redirects must run in an effect, never during render.
  //
  // `cartLoaded` is the load-bearing condition. `cartLoading` starts `false`, so
  // without it the very first pass saw "not loading, no items" and sent a customer
  // with a full cart to /cart — a direct load, a refresh, a bookmark or a shared
  // link all bounced. It only ever worked when arriving from the cart, because that
  // is a client-side route change and the provider does not remount.
  useEffect(() => {
    if (placed) return;
    if (authLoading || cartLoading || !cartLoaded) return;
    if (!user) {
      router.replace('/auth/login?redirect=/checkout');
      return;
    }
    if (cartItems.length === 0) {
      router.replace('/cart');
    }
  }, [placed, authLoading, cartLoading, cartLoaded, user, cartItems.length, router]);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const order = await ordersAPI.checkout(formData);
      // Claim the redirect before emptying the cart, so the guard above cannot
      // bounce this page to /cart while the confirmation is being pushed.
      setPlaced(true);
      await loadCart(); // Refresh cart (will be empty)
      success("Order placed successfully!");
      router.push(`/account/orders/${order.id}`);
    } catch (err) {
      error(err.message || "Checkout failed");
    } finally {
      setLoading(false);
    }
  };

  // While the confirmation is being pushed, say so rather than flashing the form
  // with an empty cart or an unexplained "Loading checkout…".
  if (placed) {
    return <div className="container section text-center">Order placed — taking you to your order…</div>;
  }

  if (authLoading || cartLoading || !cartLoaded || !user || cartItems.length === 0) {
    return <div className="container section text-center">Loading checkout…</div>;
  }

  return (
    <div className="container section">
      <h1 className="section-title mb-4">Checkout</h1>

      <div className="grid grid-2" style={{ alignItems: 'start', gridTemplateColumns: '3fr 2fr' }}>
        
        {/* Checkout Form */}
        <div className="card p-4" style={{ padding: '2rem' }}>
          <h2 style={{ fontSize: '1.4rem', borderBottom: '1px solid #eee', paddingBottom: '10px', marginBottom: '20px' }}>
            Delivery Details
          </h2>
          
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Phone Number *</label>
              <input 
                type="text" 
                name="phone"
                className="form-input" 
                value={formData.phone}
                onChange={handleChange}
                required
                placeholder="e.g. 9841234567"
              />
            </div>
            
            <div className="form-group flex gap-4">
              <div style={{ flex: 1 }}>
                <label className="form-label">Delivery Area *</label>
                <select 
                  name="shipping_city" 
                  className="form-select"
                  value={formData.shipping_city}
                  onChange={handleChange}
                  required
                  disabled={areas.length === 0}
                >
                  {areas.length === 0 && (
                    <option value="">
                      {areasError ? 'Areas unavailable' : 'Loading areas…'}
                    </option>
                  )}
                  {areas.map((area) => (
                    <option key={area.slug} value={area.slug}>
                      {area.name}{area.district && area.district !== area.name ? ` (${area.district})` : ''}
                    </option>
                  ))}
                </select>
                {areasError && (
                  <span style={{ color: 'var(--danger)', fontSize: '0.8rem' }}>
                    {areasError} Please refresh the page.
                  </span>
                )}
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Detailed Address *</label>
              <textarea 
                name="shipping_address"
                className="form-input" 
                value={formData.shipping_address}
                onChange={handleChange}
                required
                rows="3"
                placeholder="Street name, tole, house number, nearby landmark"
              ></textarea>
            </div>

            <div className="form-group">
              <label className="form-label">Delivery Notes (Optional)</label>
              <input 
                type="text" 
                name="notes"
                className="form-input" 
                value={formData.notes}
                onChange={handleChange}
                placeholder="e.g. Delivery before 10 AM"
              />
            </div>

            <h2 style={{ fontSize: '1.4rem', borderBottom: '1px solid #eee', paddingBottom: '10px', margin: '30px 0 20px' }}>
              Payment Method
            </h2>

            {paymentMocked && (
              // Shown before the choice, not after the order. A customer who picks
              // eSewa here would otherwise be told their order is "Paid" with no
              // gateway involved — the same rule the forecast page follows for
              // synthetic data, applied to money instead of numbers.
              <div
                role="note"
                style={{
                  border: '1px dashed var(--warning, #B45309)',
                  borderRadius: '8px',
                  padding: '12px 14px',
                  marginBottom: '18px',
                  fontSize: '0.88rem',
                  lineHeight: 1.5,
                  color: 'var(--text-secondary)',
                  background: 'rgba(180,83,9,0.04)',
                }}
              >
                <strong style={{ display: 'block', marginBottom: '2px' }}>
                  Demo build — no real payment is taken
                </strong>
                {`eSewa and Khalti are simulated here: choosing one marks the order paid
                  without contacting a gateway. Pick Cash on Delivery for the flow that
                  behaves as it would in production.`}
              </div>
            )}

            <div className="grid grid-3 mb-4">
              {(paymentMethods.length
                ? paymentMethods
                : [
                    // Fallback so the form is never unsubmittable if the config call
                    // failed. Matches the server's own list.
                    { value: 'cod', label: 'Cash on Delivery', is_mocked: false },
                    { value: 'esewa', label: 'eSewa', is_mocked: true },
                    { value: 'khalti', label: 'Khalti', is_mocked: true },
                  ]
              ).map((m) => {
                const selected = formData.payment_method === m.value;
                const accent = {
                  cod: 'var(--primary)',
                  esewa: '#60b52f',
                  khalti: '#5C2D91',
                }[m.value] || 'var(--primary)';
                const tint = {
                  cod: 'rgba(196,30,58,0.05)',
                  esewa: 'rgba(45,106,79,0.05)',
                  khalti: 'rgba(92,45,145,0.05)',
                }[m.value] || 'rgba(0,0,0,0.03)';

                return (
                  <label
                    key={m.value}
                    data-payment-method={m.value}
                    data-mocked={m.is_mocked ? 'true' : 'false'}
                    style={{
                      border: selected ? `2px solid ${accent}` : '1px solid #ddd',
                      padding: '15px', borderRadius: '8px', cursor: 'pointer',
                      textAlign: 'center',
                      backgroundColor: selected ? tint : 'white',
                    }}
                  >
                    <input
                      type="radio" name="payment_method" value={m.value}
                      checked={selected} onChange={handleChange}
                      style={{ display: 'none' }}
                    />
                    <span style={{ fontWeight: 'bold', color: m.value === 'cod' ? undefined : accent }}>
                      {m.value === 'cod' && '💵 '}
                      {m.label}
                    </span>
                    {m.is_mocked && (
                      // On the tile itself, not only in the banner: the banner can be
                      // scrolled past, and the label is what makes the choice honest
                      // at the moment it is made.
                      <span
                        style={{
                          display: 'block', fontSize: '0.7rem', letterSpacing: '0.04em',
                          textTransform: 'uppercase', color: '#B45309', marginTop: '4px',
                        }}
                      >
                        Simulated
                      </span>
                    )}
                  </label>
                );
              })}
            </div>

            <button type="submit" className="btn btn-primary btn-lg" style={{width: '100%'}} disabled={loading}>
              {loading ? 'Processing...' : `Place Order (Rs. ${cartTotal})`}
            </button>
          </form>
        </div>

        {/* Order Summary Sidebar */}
        <div className="card" style={{ padding: '1.5rem', position: 'sticky', top: '90px' }}>
          <h3 style={{ fontSize: '1.2rem', marginBottom: '15px' }}>Order Overview</h3>
          
          <div style={{ maxHeight: '300px', overflowY: 'auto', marginBottom: '15px' }}>
            {cartItems.map(item => (
              <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', fontSize: '0.9rem' }}>
                <span style={{color: 'var(--text-secondary)'}}>
                  {item.quantity}x {item.product_detail.name}
                </span>
                <span style={{fontWeight: '600'}}>Rs. {item.subtotal}</span>
              </div>
            ))}
          </div>
          
          <div style={{ borderTop: '1px solid #eee', paddingTop: '15px', display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
            <span>Subtotal</span>
            <span>Rs. {cartSubtotal}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '15px', color: 'var(--text-secondary)' }}>
            <span>Delivery</span>
            <span>Rs. {deliveryFee}</span>
          </div>
          
          <div style={{ borderTop: '2px solid #eee', paddingTop: '15px', display: 'flex', justifyContent: 'space-between', fontWeight: 'bold', fontSize: '1.2rem', color: 'var(--primary)' }}>
            <span>Total</span>
            <span>Rs. {cartTotal}</span>
          </div>
        </div>

      </div>
    </div>
  );
}
