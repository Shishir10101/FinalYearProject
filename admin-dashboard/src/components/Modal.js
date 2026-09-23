'use client';
import { useEffect } from 'react';

/**
 * Accessible modal dialog.
 *
 * Closes on Escape and on backdrop click. Locks body scroll while open so the
 * table behind it does not drift. Kept deliberately small — the dashboard has
 * three CRUD surfaces and they should not each re-implement this.
 */
export default function Modal({ title, onClose, children, footer, wide = false }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        // Only close when the backdrop itself was pressed, not the dialog.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal"
        style={wide ? { maxWidth: '760px' } : undefined}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Close dialog"
          >
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
