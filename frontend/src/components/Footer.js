import Link from 'next/link';
import styles from './Footer.module.css';

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.mandalaTop}></div>
      <div className={styles.container}>
        <div className={styles.grid}>
          <div className={styles.col}>
            <div className={styles.brand}>
              <span className={styles.brandIcon}>🪔</span>
              <h3>Puja Sewa</h3>
            </div>
            <p className={styles.desc}>
              Your trusted source for puja samagri in Kathmandu Valley. 
              Quality products for every ritual and festival.
            </p>
            <div className={styles.cities}>
              <span>📍 Kathmandu</span>
              <span>📍 Lalitpur</span>
              <span>📍 Bhaktapur</span>
            </div>
          </div>

          <div className={styles.col}>
            <h4>Quick Links</h4>
            <Link href="/products">All Products</Link>
            <Link href="/festivals">Festival Kits</Link>
            <Link href="/pujas">Shop by Ritual</Link>
            <Link href="/recommendations">Recommendations</Link>
            <Link href="/cart">Cart</Link>
          </div>

          <div className={styles.col}>
            {/* "Occasions", not "Festivals": Bratabandha below is a rite of
                passage, not a festival — the same conflation the Puja model
                exists to untangle. */}
            <h4>Occasions</h4>
            <Link href="/festivals?type=dashain">Dashain</Link>
            <Link href="/festivals?type=tihar">Tihar</Link>
            <Link href="/festivals?type=shivaratri">Shivaratri</Link>
            <Link href="/festivals?type=bratabandha">Bratabandha</Link>
          </div>

          <div className={styles.col}>
            <h4>Contact</h4>
            <p>📞 +977-1-4XXXXXX</p>
            <p>📧 info@pujasewa.com.np</p>
            <p>📍 Asan, Kathmandu</p>
            <div className={styles.social}>
              <span>📘</span>
              <span>📸</span>
              <span>🐦</span>
            </div>
          </div>
        </div>

        <div className={styles.bottom}>
          <p>© 2026 Puja Sewa. All rights reserved.</p>
          <p className={styles.tagline}>🙏 शुभ पूजा, शुभ परिणाम 🙏</p>
        </div>
      </div>
    </footer>
  );
}
