'use client';
import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { productsAPI } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import styles from './ReviewsSection.module.css';

/**
 * Ratings and reviews for one product.
 *
 * A product page with no social proof was the gap `docs/FEATURES.md` named, and
 * `docs/DATABASE-DESIGN.md` listed the missing `Review` table as a known omission.
 *
 * One API call returns everything this renders — the summary, the page of reviews,
 * the total, and the signed-in reader's own review — because splitting them would
 * mean three round-trips to draw one section, and the summary would have to be
 * reassembled on the client.
 *
 * @param {string} slug     The product being reviewed.
 * @param {number} initialAverage  From the product payload, so the stars can render
 *                                 before the reviews arrive. Refreshed from the
 *                                 review response once it lands.
 * @param {number} initialCount
 * @param {function} [onSummaryChange] Called with (average, count) after any write,
 *                                 so the caller can keep its own header in step.
 */

const STARS = [5, 4, 3, 2, 1];

function Stars({ value, size = 'md' }) {
  const rounded = Math.round(value || 0);
  return (
    <span
      className={`${styles.stars} ${size === 'lg' ? styles.starsLg : ''}`}
      role="img"
      aria-label={value ? `${value} out of 5 stars` : 'No rating yet'}
    >
      {STARS.slice().reverse().map((n) => (
        <span key={n} className={n <= rounded ? styles.starOn : styles.starOff} aria-hidden="true">★</span>
      ))}
    </span>
  );
}

export default function ReviewsSection({ slug, initialAverage, initialCount, onSummaryChange }) {
  const { user, loading: authLoading } = useAuth();
  const { success, error: toastError } = useToast();
  const pathname = usePathname();

  const [summary, setSummary] = useState({
    average_rating: initialAverage ?? null,
    review_count: initialCount ?? 0,
    distribution: null,
  });
  const [reviews, setReviews] = useState([]);
  const [mine, setMine] = useState(null);
  const [count, setCount] = useState(initialCount ?? 0);
  const [page, setPage] = useState(1);

  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({ rating: 5, title: '', body: '' });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  /**
   * `onSummaryChange` is held in a ref, deliberately **not** in `load`'s dependencies.
   *
   * `load` is the dependency of the mount effect below, so anything in its dep list
   * that changes identity on every render re-fires that effect forever. Callers pass
   * this callback as an inline arrow — the obvious way to write it — which is a new
   * function on every parent render. Depending on it produced a genuine loop:
   *
   *     load() → onSummaryChange() → parent setState → parent re-render →
   *     new arrow → new `load` identity → effect fires → load() …
   *
   * Measured on the product page: **537 requests to the reviews endpoint in 12
   * seconds and still climbing**, with the section flickering between skeletons and
   * content. Nothing caught it — not the build, not ESLint, not 336 unit tests and
   * not 575 live API assertions. Only driving the page in a browser did.
   *
   * A ref keeps the latest callback without making it an identity dependency, so the
   * component is safe by construction rather than by every caller remembering.
   */
  const onSummaryRef = useRef(onSummaryChange);
  useEffect(() => { onSummaryRef.current = onSummaryChange; }, [onSummaryChange]);

  const load = useCallback(async (nextPage = 1, append = false) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    setLoadError('');
    try {
      const data = await productsAPI.reviews(slug, nextPage);
      setSummary(data.summary || {});
      setCount(data.count ?? 0);
      setMine(data.mine || null);
      setReviews((prev) => (append ? [...prev, ...(data.results || [])] : (data.results || [])));
      setPage(nextPage);
      if (onSummaryRef.current) {
        onSummaryRef.current(
          data.summary?.average_rating ?? null,
          data.summary?.review_count ?? 0,
        );
      }
    } catch (e) {
      // Never render a backend failure as "no reviews yet" — that tells the shopper
      // something false about the product.
      setLoadError(e.message || 'Could not load reviews.');
      if (!append) setReviews([]);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [slug]);

  useEffect(() => { load(1, false); }, [load]);

  // Prefill the form when the reader already has a review, so "Edit" shows what they
  // wrote rather than an empty box they might overwrite by accident.
  useEffect(() => {
    if (mine) {
      setForm({ rating: mine.rating, title: mine.title || '', body: mine.body || '' });
    }
  }, [mine]);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setFormError('');
    try {
      await productsAPI.submitReview(slug, {
        rating: Number(form.rating),
        title: form.title,
        body: form.body,
      });
      success(mine ? 'Your review was updated.' : 'Thanks — your review is published.');
      setFormOpen(false);
      await load(1, false);
    } catch (err) {
      // The API returns `{body: ["..."]}` for the "a rating needs words" rule.
      const fields = err.fields || {};
      const message = fields.body?.[0] || fields.rating?.[0] || fields.title?.[0]
        || err.message || 'Could not save your review.';
      setFormError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async () => {
    if (!mine) return;
    setSubmitting(true);
    try {
      await productsAPI.deleteReview(mine.id);
      success('Your review was removed.');
      setMine(null);
      setForm({ rating: 5, title: '', body: '' });
      setFormOpen(false);
      await load(1, false);
    } catch (err) {
      toastError(err.message || 'Could not remove your review.');
    } finally {
      setSubmitting(false);
    }
  };

  const hasReviews = count > 0;
  const shown = reviews.length;

  return (
    <section className={styles.wrap} id="reviews" aria-labelledby="reviews-heading">
      <h2 className="section-title" id="reviews-heading">Ratings &amp; Reviews</h2>

      {/* --- summary -------------------------------------------------- */}
      <div className={styles.summaryCard}>
        <div className={styles.summaryScore}>
          <span className={styles.scoreNumber}>
            {summary.average_rating != null ? summary.average_rating.toFixed(1) : '—'}
          </span>
          <Stars value={summary.average_rating} size="lg" />
          <span className={styles.scoreCount}>
            {hasReviews
              ? `${count} review${count === 1 ? '' : 's'}`
              : 'No reviews yet'}
          </span>
        </div>

        <div className={styles.distribution}>
          {STARS.map((n) => {
            const total = summary.distribution?.[String(n)] ?? 0;
            const pct = count > 0 ? Math.round((total / count) * 100) : 0;
            return (
              <div className={styles.distRow} key={n}>
                <span className={styles.distLabel}>{n} ★</span>
                <span className={styles.distTrack}>
                  <span className={styles.distFill} style={{ width: `${pct}%` }} />
                </span>
                <span className={styles.distCount}>{total}</span>
              </div>
            );
          })}
        </div>

        <div className={styles.summaryAction}>
          {authLoading ? (
            <div className="skeleton-block" style={{ height: '40px', width: '170px' }} />
          ) : !user ? (
            <Link
              href={`/auth/login?redirect=${encodeURIComponent(pathname || `/products/${slug}`)}`}
              className="btn btn-outline"
            >
              Log in to review
            </Link>
          ) : mine ? (
            <button
              className="btn btn-outline"
              onClick={() => setFormOpen((v) => !v)}
              disabled={submitting}
            >
              {formOpen ? 'Cancel' : 'Edit your review'}
            </button>
          ) : (
            <button
              className="btn btn-primary"
              onClick={() => setFormOpen((v) => !v)}
              disabled={submitting}
            >
              {formOpen ? 'Cancel' : 'Write a review'}
            </button>
          )}
        </div>
      </div>

      {/* --- the form ------------------------------------------------- */}
      {formOpen && user && (
        <form className={styles.form} onSubmit={submit}>
          <h3 className={styles.formTitle}>
            {mine ? 'Edit your review' : 'Write a review'}
          </h3>

          {formError && <div className="notice notice-error" role="alert">{formError}</div>}

          <div className="form-group">
            <label className="form-label" htmlFor="review-rating">Your rating</label>
            <div className={styles.ratingPicker} id="review-rating">
              {STARS.slice().reverse().map((n) => (
                <button
                  type="button"
                  key={n}
                  className={n <= form.rating ? styles.starBtnOn : styles.starBtnOff}
                  aria-label={`${n} star${n === 1 ? '' : 's'}`}
                  aria-pressed={n === form.rating}
                  onClick={() => setForm({ ...form, rating: n })}
                >
                  ★
                </button>
              ))}
              <span className={styles.ratingWord}>
                {['', 'Poor', 'Fair', 'Good', 'Very good', 'Excellent'][form.rating]}
              </span>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="review-title">Title</label>
            <input
              id="review-title"
              className="form-input"
              type="text"
              maxLength={120}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Sum it up in a few words"
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="review-body">Your review</label>
            <textarea
              id="review-body"
              className="form-input"
              rows="4"
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
              placeholder="What did you think of the quality, the packaging, the value?"
            />
            <span className="field-hint">
              A rating on its own is not much help to the next shopper — add a line.
            </span>
          </div>

          <div className={styles.formActions}>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Saving…' : mine ? 'Save changes' : 'Publish review'}
            </button>
            {mine && (
              <button
                type="button"
                className="btn btn-outline"
                onClick={remove}
                disabled={submitting}
              >
                Delete my review
              </button>
            )}
          </div>
        </form>
      )}

      {/* --- your own review, when it is not in the list --------------- */}
      {mine && !formOpen && (
        <div className={styles.mineCard}>
          <div className={styles.mineHead}>
            <strong>Your review</strong>
            <Stars value={mine.rating} />
          </div>
          {mine.title && <p className={styles.reviewTitle}>{mine.title}</p>}
          {mine.body && <p className={styles.reviewBody}>{mine.body}</p>}
        </div>
      )}

      {/* --- the list ------------------------------------------------- */}
      {loading ? (
        <div className={styles.list}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton-block" style={{ height: '96px', borderRadius: 'var(--radius-md)' }} />
          ))}
        </div>
      ) : loadError ? (
        <div className="empty-state">
          <div className="empty-state-icon">⚠️</div>
          <h3 className="empty-state-title">Could not load reviews</h3>
          <p className="empty-state-text">{loadError}</p>
          <button className="btn btn-primary" style={{ marginTop: '16px' }} onClick={() => load(1, false)}>
            Try again
          </button>
        </div>
      ) : count === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">✍️</div>
          <h3 className="empty-state-title">No reviews yet</h3>
          <p className="empty-state-text">
            {user
              ? 'Be the first to say what you think of this one.'
              : 'Log in to be the first to review it.'}
          </p>
        </div>
      ) : (
        <>
          <ul className={styles.list}>
            {reviews.map((review) => (
              <li className={styles.review} key={review.id}>
                <div className={styles.reviewHead}>
                  <div>
                    <strong className={styles.author}>{review.author}</strong>
                    {review.is_verified_purchase && (
                      <span className={`badge badge-success ${styles.verified}`}>
                        ✓ Verified purchase
                      </span>
                    )}
                  </div>
                  <time className={styles.reviewDate} dateTime={review.created_at}>
                    {new Date(review.created_at).toLocaleDateString()}
                  </time>
                </div>
                <Stars value={review.rating} />
                {review.title && <p className={styles.reviewTitle}>{review.title}</p>}
                {review.body && <p className={styles.reviewBody}>{review.body}</p>}
              </li>
            ))}
          </ul>

          {shown < count && (
            <div className={styles.moreRow}>
              <button
                className="btn btn-outline"
                onClick={() => load(page + 1, true)}
                disabled={loadingMore}
              >
                {loadingMore ? 'Loading…' : `Show more (${count - shown} left)`}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
