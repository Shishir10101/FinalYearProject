'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { useCart } from '@/context/CartContext';
import { useWishlist } from '@/context/WishlistContext';
import styles from './Navbar.module.css';

export default function Navbar() {
  const { user, logout } = useAuth();
  const { cartCount } = useCart();
  const { wishlistCount } = useWishlist();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  return (
    <nav className={styles.navbar}>
      <div className={styles.container}>
        <Link href="/" className={styles.logo}>
          <span className={styles.logoIcon}>🪔</span>
          <div>
            <span className={styles.logoText}>Puja Sewa</span>
            <span className={styles.logoSub}>Store Nepal</span>
          </div>
        </Link>

        <div className={`${styles.navLinks} ${mobileOpen ? styles.navLinksOpen : ''}`}>
          <Link href="/" className={styles.navLink} onClick={() => setMobileOpen(false)}>Home</Link>
          <Link href="/products" className={styles.navLink} onClick={() => setMobileOpen(false)}>Products</Link>
          <Link href="/festivals" className={styles.navLink} onClick={() => setMobileOpen(false)}>Festival Kits</Link>
          <Link href="/pujas" className={styles.navLink} onClick={() => setMobileOpen(false)}>Rituals</Link>
          <Link href="/recommendations" className={styles.navLink} onClick={() => setMobileOpen(false)}>Recommendations</Link>
        </div>

        <div className={styles.navActions}>
          <Link href="/cart" className={styles.cartBtn}>
            🛒
            {cartCount > 0 && <span className={styles.cartBadge}>{cartCount}</span>}
          </Link>

          {/* Shown to guests too: the page behind it explains what a wishlist is and
              sends them to login, which is friendlier than hiding the affordance and
              letting them wonder where the heart on a product card leads. */}
          <Link
            href="/wishlist"
            className={styles.wishBtn}
            aria-label={
              wishlistCount > 0
                ? `My wishlist, ${wishlistCount} saved item${wishlistCount === 1 ? '' : 's'}`
                : 'My wishlist'
            }
          >
            ♡
            {wishlistCount > 0 && <span className={styles.wishBadge}>{wishlistCount}</span>}
          </Link>

          {user ? (
            <div className={styles.profileWrapper}>
              <button
                className={styles.profileBtn}
                onClick={() => setProfileOpen(!profileOpen)}
              >
                <span className={styles.avatar}>
                  {user.first_name ? user.first_name[0] : user.username[0]}
                </span>
              </button>
              {profileOpen && (
                <div className={styles.dropdown}>
                  <div className={styles.dropdownHeader}>
                    <strong>{user.first_name || user.username}</strong>
                    <small>{user.email}</small>
                  </div>
                  <Link href="/account" className={styles.dropdownItem} onClick={() => setProfileOpen(false)}>
                    👤 My Profile
                  </Link>
                  <Link href="/account/orders" className={styles.dropdownItem} onClick={() => setProfileOpen(false)}>
                    📦 My Orders
                  </Link>
                  <Link href="/wishlist" className={styles.dropdownItem} onClick={() => setProfileOpen(false)}>
                    ♡ My Wishlist
                  </Link>
                  <button className={styles.dropdownItem} onClick={() => { logout(); setProfileOpen(false); }}>
                    🚪 Logout
                  </button>
                </div>
              )}
            </div>
          ) : (
            <Link href="/auth/login" className={`btn btn-primary btn-sm`}>
              Login
            </Link>
          )}

          <button className={styles.hamburger} onClick={() => setMobileOpen(!mobileOpen)}>
            {mobileOpen ? '✕' : '☰'}
          </button>
        </div>
      </div>
    </nav>
  );
}
