import './globals.css';
import { AuthProvider } from '@/context/AuthContext';
import { CartProvider } from '@/context/CartContext';
import { ToastProvider } from '@/context/ToastContext';
import { WishlistProvider } from '@/context/WishlistContext';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';

export const metadata = {
  title: 'Puja Sewa | पूजा सेवा',
  // The description and keywords deliberately keep "puja samagri" — that is what
  // the shop *sells* (the merchandise category), whereas "Puja Sewa" is the
  // store's name. Search traffic arrives on the goods, not on the brand.
  description: 'Your one-stop shop for all puja samagri in Kathmandu Valley. Festival kits, ritual supplies, and more delivered to your doorstep.',
  keywords: 'puja samagri, Nepal, Kathmandu, festival, Dashain, Tihar, ritual supplies, pooja items',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="/favicon.ico" />
      </head>
      <body>
        <ToastProvider>
          <AuthProvider>
            <WishlistProvider>
              <CartProvider>
                <Navbar />
                <main style={{ minHeight: '70vh' }}>
                  {children}
                </main>
                <Footer />
              </CartProvider>
            </WishlistProvider>
          </AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
