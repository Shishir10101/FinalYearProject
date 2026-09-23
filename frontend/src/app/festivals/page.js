'use client';
import { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { festivalsAPI } from '@/lib/api';
import { useCart } from '@/context/CartContext';
import { useToast } from '@/context/ToastContext';
import styles from './festivals.module.css';

function FestivalsContent() {
  const searchParams = useSearchParams();
  const initialType = searchParams.get('type') || '';
  
  const [kits, setKits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeType, setActiveType] = useState(initialType);
  const [selectedKit, setSelectedKit] = useState(null);
  // Starts with just "All Festivals" and fills in from the real kit data.
  const [typeOptions, setTypeOptions] = useState([{ value: '', label: 'All Festivals' }]);

  const { addKitToCart } = useCart();
  const { success, error } = useToast();

  useEffect(() => {
    // The filter used to be a hardcoded list of seven festival types. That is the
    // same trap as the old hardcoded CITY_CHOICES: the moment an admin adds a kit
    // for a festival type nobody listed, it exists but is unreachable through the
    // UI. Deriving the chips from the kits that actually exist cannot drift.
    const loadTypeOptions = async () => {
      try {
        const data = await festivalsAPI.kits();
        const all = Array.isArray(data) ? data : (data.results || []);
        const seen = new Map();
        all.forEach((kit) => {
          if (kit.festival_type && !seen.has(kit.festival_type)) {
            seen.set(kit.festival_type, kit.festival_type_display || kit.festival_type);
          }
        });
        setTypeOptions([
          { value: '', label: 'All Festivals' },
          ...[...seen.entries()]
            .sort((a, b) => a[1].localeCompare(b[1]))
            .map(([value, label]) => ({ value, label })),
        ]);
      } catch (e) {
        // Leave the single "All Festivals" chip: the page still works.
        console.error(e);
      }
    };
    loadTypeOptions();
  }, []);

  useEffect(() => {
    fetchKits();
  }, [activeType]);

  const fetchKits = async () => {
    setLoading(true);
    try {
      const data = await festivalsAPI.kits(activeType);
      setKits(data);
    } catch (e) {
      console.error(e);
      error("Failed to load festival kits");
    } finally {
      setLoading(false);
    }
  };

  const fetchKitDetail = async (id) => {
    try {
      const data = await festivalsAPI.kitDetail(id);
      setSelectedKit(data);
    } catch (e) {
      error("Failed to load kit details");
    }
  };

  const handleAddKit = async (kitId, kitName) => {
    try {
      await addKitToCart(kitId);
      success(`Added ${kitName} to cart successfully`);
      setSelectedKit(null); // Close modal
    } catch (e) {
      error("Failed to add kit to cart");
    }
  };

  return (
    <div className="container section">
      <div className={styles.header}>
        <h1 className="section-title">Festival & Ritual Kits</h1>
        <p className="section-subtitle">Complete, curated sets of authentic samagri for your specific puja needs based on traditional requirements.</p>
        
        <div className={styles.tabs}>
          {typeOptions.map(type => (
            <button 
              key={type.value}
              className={`${styles.tabBtn} ${activeType === type.value ? styles.activeTab : ''}`}
              onClick={() => setActiveType(type.value)}
            >
              {type.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-3">
          {[1,2,3].map(i => <div key={i} className="card skeleton" style={{height: '300px'}}></div>)}
        </div>
      ) : kits.length === 0 ? (
        <div className={styles.emptyState}>
          <span className={styles.emptyIcon}>🙏</span>
          <h3>
            {activeType
              ? 'No ready-made kit for this festival yet'
              : 'No kits found'}
          </h3>
          <p>
            {activeType
              ? 'We have not put a kit together for this one. The recommender can still tell you what you will need.'
              : 'Please check back later or browse our individual products.'}
          </p>
          <div className={styles.emptyActions}>
            {activeType && (
              <button className="btn btn-outline" onClick={() => setActiveType('')}>
                Show all festivals
              </button>
            )}
            <Link href="/recommendations" className="btn btn-primary">
              See what you need
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-3">
          {kits.map(kit => (
            <div key={kit.id} className={`card ${styles.kitCard}`}>
              <div className={styles.kitHeader}>
                <span className="badge badge-secondary">{kit.festival_type_display}</span>
                {kit.discount_percent > 0 && (
                  <span className={styles.discountBadge}>{kit.discount_percent}% OFF</span>
                )}
              </div>
              
              <div className={styles.kitBody}>
                <h3>{kit.name}</h3>
                <p className={styles.kitDesc}>{kit.description}</p>
                
                <div className={styles.kitStats}>
                  <span>📦 {kit.item_count} Items Included</span>
                </div>
                
                <div className={styles.priceRow}>
                  <div className={styles.priceCol}>
                    {kit.discount_percent > 0 && (
                      <span className={styles.originalPrice}>Rs. {kit.original_price}</span>
                    )}
                    <span className={styles.price}>Rs. {kit.total_price}</span>
                  </div>
                  <button 
                    className="btn btn-outline btn-sm"
                    onClick={() => fetchKitDetail(kit.id)}
                  >
                    View Details
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Kit Detail Modal */}
      {selectedKit && (
        <div className={styles.modalOverlay} onClick={() => setSelectedKit(null)}>
          <div className={styles.modalContent} onClick={e => e.stopPropagation()}>
            <button className={styles.closeBtn} onClick={() => setSelectedKit(null)}>✕</button>
            
            <div className={styles.modalHeader}>
              <span className="badge badge-secondary">{selectedKit.festival_type_display}</span>
              <h2>{selectedKit.name}</h2>
              <p>{selectedKit.description}</p>
            </div>
            
            <div className={styles.modalBody}>
              <h3>Included Items ({selectedKit.items.length})</h3>
              <ul className={styles.itemList}>
                {selectedKit.items.map(item => (
                  <li key={item.id} className={styles.itemRow}>
                    <div className={styles.itemImg}>
                      {item.product_detail.image ? (
                        <img src={item.product_detail.image} alt={item.product_detail.name} />
                      ) : (
                        <span>🪔</span>
                      )}
                    </div>
                    <div className={styles.itemInfo}>
                      <h4>{item.product_detail.name}</h4>
                      <span>Rs. {item.product_detail.price} x {item.quantity} {item.product_detail.unit}</span>
                    </div>
                    <div className={styles.itemStatus}>
                      {item.is_required ? (
                        <span className="badge badge-primary">Required</span>
                      ) : (
                        <span className="badge badge-warning">Optional Addition</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            
            <div className={styles.modalFooter}>
              <div className={styles.modalPrice}>
                <span>Total Kit Price:</span>
                <strong>Rs. {selectedKit.total_price}</strong>
                {selectedKit.discount_percent > 0 && (
                  <small>You save Rs. {(selectedKit.original_price - selectedKit.total_price).toFixed(2)}!</small>
                )}
              </div>
              <button 
                className="btn btn-primary btn-lg"
                onClick={() => handleAddKit(selectedKit.id, selectedKit.name)}
              >
                Add Complete Kit to Cart
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function FestivalsPage() {
  return (
    <Suspense fallback={<div className="container section text-center">Loading...</div>}>
      <FestivalsContent />
    </Suspense>
  );
}
