'use client';
import { createContext, useContext, useState, useCallback, useMemo } from 'react';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3000);
  }, []);

  // `useCallback` and a memoised value, not bare arrow functions in an inline
  // object. Unstable here is not a micro-optimisation: any consumer that puts
  // `error` in a `useCallback` dependency list re-creates its own callback on every
  // render, which re-fires the effect that depends on it — an unbounded fetch loop.
  // That is exactly what happened to the reviews section on the product page (537
  // requests in 12 seconds), and the product page below would have hit the same
  // trap the moment its loader became a `useCallback`. Fixing it here removes the
  // hazard for every consumer rather than making each one remember.
  const success = useCallback((msg) => addToast(msg, 'success'), [addToast]);
  const error = useCallback((msg) => addToast(msg, 'error'), [addToast]);
  const info = useCallback((msg) => addToast(msg, 'info'), [addToast]);

  const value = useMemo(() => ({ success, error, info }), [success, error, info]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/*
        A toast appears *after* an action, so a screen reader will not encounter
        it by reading order — it needs a live region. `aria-live` plus a matching
        `role` makes the announcement reliable in both NVDA and VoiceOver.
      */}
      <div className="toast-container" aria-live="polite" aria-atomic="false">
        {toasts.map(t => (
          <div
            key={t.id}
            className={`toast toast-${t.type}`}
            role={t.type === 'error' ? 'alert' : 'status'}
            aria-live={t.type === 'error' ? 'assertive' : 'polite'}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used within ToastProvider');
  return context;
}
