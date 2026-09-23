'use client';
import { useState } from 'react';
import Link from 'next/link';
import { cartAPI } from '@/lib/api';
import { useCart } from '@/context/CartContext';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import styles from '@/app/pujas/pujas.module.css';

/**
 * "Add essentials to cart" for a ritual.
 *
 * Extracted as its own client component so the ritual page around it can stay a
 * Server Component — the lists of samagri are public data and need no client
 * boundary, only this button does.
 */
export default function AddPujaButton({ pujaId, slug, itemCount }) {
  const [adding, setAdding] = useState(false);
  const { loadCart } = useCart();
  const { user, loading: authLoading } = useAuth();
  const { success, error: toastError } = useToast();

  const handleAdd = async () => {
    setAdding(true);
    try {
      const result = await cartAPI.addPuja(pujaId);
      await loadCart();

      if (result?.skipped?.length) {
        // Report exactly what was left out. A clean "added!" here would be a lie.
        toastError(`${result.added} added. Out of stock: ${result.skipped.join(', ')}`);
      } else {
        success(`${result.added} items added to your cart`);
      }
    } catch (e) {
      toastError(e.message || 'Could not add these items to your cart.');
    } finally {
      setAdding(false);
    }
  };

  // The cart endpoint requires a token. Offering a button that would fail with
  // "session expired" to someone who was never signed in reads as nonsense, so a
  // signed-out visitor gets the login route instead.
  if (authLoading) {
    return <div className="skeleton-block" style={{ height: '44px' }} />;
  }

  if (!user) {
    return (
      <Link
        href={`/auth/login?redirect=/pujas/${slug}`}
        className="btn btn-primary"
        style={{ width: '100%', display: 'block', textAlign: 'center' }}
      >
        Log in to add these
      </Link>
    );
  }

  return (
    <button
      className="btn btn-primary"
      style={{ width: '100%' }}
      onClick={handleAdd}
      disabled={adding || itemCount === 0}
    >
      {adding ? 'Adding…' : 'Add essentials to cart'}
    </button>
  );
}
