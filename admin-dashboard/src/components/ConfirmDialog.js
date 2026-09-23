'use client';
import Modal from './Modal';

/**
 * Confirmation dialog for destructive actions.
 *
 * The dashboard deletes products and categories. A bare `window.confirm` is
 * blocking, unstyled, and untestable — this keeps the four-state discipline
 * (loading / success / empty / error) applied to the confirm step itself.
 */
export default function ConfirmDialog({
  title = 'Are you sure?',
  body,
  confirmLabel = 'Delete',
  busy = false,
  onConfirm,
  onCancel,
}) {
  return (
    <Modal
      title={title}
      onClose={busy ? () => {} : onCancel}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? 'Working…' : confirmLabel}
          </button>
        </>
      }
    >
      <p style={{ margin: 0, lineHeight: 1.6 }}>{body}</p>
    </Modal>
  );
}
