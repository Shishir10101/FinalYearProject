'use client';
import { useState, useEffect, useRef } from 'react';

/**
 * Pick an image for a product or a kit, with a preview.
 *
 * Built once and shared, because the products screen and the kit editor need the
 * same control and a second copy would drift — which is exactly what happened to the
 * storefront's product cards before `ProductCard` was extracted.
 *
 * **Why this exists at all.** `Product.image`, `Category.image` and `FestivalKit.image`
 * are real columns that the seed data populates, and until now *nothing in either
 * dashboard could set one*. `docs/FEATURES.md` carried it as a ⚠️: "products have an
 * `image` column, but no upload widget in either dashboard screen". A shopkeeper
 * adding a product got the placeholder lamp forever.
 *
 * It is a **controlled-ish** component: it does not hold the file, it reports it
 * upward via `onSelect`. The parent owns the file because the parent owns the submit,
 * and a child that both held the file and could not submit it would just be a state
 * duplication waiting to disagree.
 *
 * `onSelect(null)` means "remove the image"; the parent turns that into a request
 * that clears the column.
 */

const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPT = 'image/png,image/jpeg,image/webp,image/gif';

export default function ImageField({
  currentUrl, onSelect, label = 'Image', hint, disabled = false, error,
}) {
  const [preview, setPreview] = useState(null);
  const [localError, setLocalError] = useState('');
  // The blob URL of the *pending* selection, held so it can be revoked. Without
  // this every file pick leaks an object URL for the life of the tab, and picking
  // ten images in one session holds ten decoded bitmaps in memory.
  const objectUrl = useRef(null);

  useEffect(() => () => {
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
  }, []);

  const handleChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      setLocalError('That file is not an image.');
      event.target.value = '';
      return;
    }
    if (file.size > MAX_BYTES) {
      // Checked here rather than letting the upload fail: a 6 MB phone photo would
      // otherwise upload fully and then be rejected, which wastes the upload and
      // tells the user nothing useful.
      setLocalError(
        `That image is ${(file.size / 1024 / 1024).toFixed(1)} MB. The limit is 5 MB.`
      );
      event.target.value = '';
      return;
    }

    setLocalError('');
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = URL.createObjectURL(file);
    setPreview(objectUrl.current);
    onSelect(file);
  };

  const handleClear = () => {
    if (objectUrl.current) {
      URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = null;
    }
    setPreview(null);
    setLocalError('');
    // `null` is a meaningful value here — "remove the image" — not "no change".
    onSelect(null);
  };

  const shown = preview || currentUrl;
  const message = localError || error;

  return (
    <div className="field">
      <label htmlFor="image-input">{label}</label>

      <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div
          style={{
            width: '92px',
            height: '92px',
            flex: '0 0 auto',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)',
            background: 'var(--bg-secondary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
          }}
        >
          {shown ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={shown}
              alt="Current image"
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          ) : (
            <span style={{ fontSize: '1.6rem', opacity: 0.4 }} aria-hidden="true">🪔</span>
          )}
        </div>

        <div style={{ flex: '1 1 200px', minWidth: '180px' }}>
          <input
            id="image-input"
            type="file"
            accept={ACCEPT}
            onChange={handleChange}
            disabled={disabled}
            aria-describedby={message ? 'image-error' : 'image-hint'}
            className={message ? 'input-invalid' : ''}
          />
          <div style={{ marginTop: '8px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {shown && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={handleClear}
                disabled={disabled}
              >
                Remove image
              </button>
            )}
          </div>
          {message ? (
            <span className="field-error" id="image-error">{message}</span>
          ) : (
            <span className="field-hint" id="image-hint">
              {hint || 'PNG, JPEG, WebP or GIF, up to 5 MB. Shown on the storefront card.'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
