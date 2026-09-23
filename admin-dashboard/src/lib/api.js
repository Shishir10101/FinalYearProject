const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

const TOKEN_KEY = 'admin_token';

class AdminApiClient {
  getToken() {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(TOKEN_KEY);
    }
    return null;
  }

  /**
   * Shared response handling for every request, JSON or multipart.
   *
   * Extracted so `upload()` cannot drift from `request()`: a 401 on an upload must
   * clear the token and say the same thing as a 401 on a read, and a DRF field error
   * must land on `err.body` either way so the forms can highlight the input.
   */
  async handle(res) {
    if (res.status === 401 || res.status === 403) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem(TOKEN_KEY);
      }
      throw new Error(
        res.status === 401
          ? 'Your session has expired. Please log in again.'
          : 'You do not have permission to perform this action.'
      );
    }

    if (!res.ok) {
      // Surface the server's own validation message where one exists, without
      // leaking internal detail (no stack traces, no raw exception strings).
      let detail = null;
      let body = null;
      try {
        body = await res.json();
        if (typeof body?.detail === 'string') detail = body.detail;
        else if (typeof body?.error === 'string') detail = body.error;
        else if (Array.isArray(body?.non_field_errors)) detail = body.non_field_errors[0];
      } catch {
        // non-JSON error body — fall through to the generic message
      }
      const err = new Error(
        detail || `Request failed (${res.status}). Please try again.`
      );
      // Keep the parsed body so a form can highlight the offending field rather
      // than dumping one generic banner. See `fieldErrors()` below.
      err.status = res.status;
      err.body = body;
      throw err;
    }

    if (res.status === 204) return null;
    return res.json();
  }

  async request(endpoint, options = {}) {
    const url = `${API_URL}${endpoint}`;
    const token = this.getToken();

    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (token) headers['Authorization'] = `Bearer ${token}`;

    let res;
    try {
      res = await fetch(url, { ...options, headers });
    } catch (e) {
      // Network-level failure (backend down, DNS, offline).
      throw new Error('Cannot reach the server. Is the backend running?');
    }

    return this.handle(res);
  }

  /**
   * Upload a file, with any extra scalar fields alongside it.
   *
   * **`Content-Type` is deliberately not set.** The browser must generate
   * `multipart/form-data; boundary=…` itself; setting the header by hand omits the
   * boundary, and DRF then reports an empty body rather than a usable error. That
   * is the whole reason this cannot just reuse `request()`.
   *
   * `PATCH` by default, because the only caller is an editor updating an existing
   * row. A PATCH with multipart is valid: DRF parses the body first and then applies
   * partial-update semantics to whatever fields arrived.
   */
  async upload(endpoint, formData, method = 'PATCH') {
    const url = `${API_URL}${endpoint}`;
    const token = this.getToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let res;
    try {
      res = await fetch(url, { method, headers, body: formData });
    } catch (e) {
      throw new Error('Cannot reach the server. Is the backend running?');
    }

    return this.handle(res);
  }

  get(e) { return this.request(e, { method: 'GET' }); }
  post(e, d) { return this.request(e, { method: 'POST', body: JSON.stringify(d) }); }
  put(e, d) { return this.request(e, { method: 'PUT', body: JSON.stringify(d) }); }
  patch(e, d) { return this.request(e, { method: 'PATCH', body: JSON.stringify(d) }); }
  delete(e) { return this.request(e, { method: 'DELETE' }); }
}

export const api = new AdminApiClient();
export default api;

/**
 * Turn a DRF error body into a `{ field: message }` map for inline display.
 *
 * DRF returns `{"price": ["Ensure this value is greater than 0."]}`. The admin
 * forms render one message per field, so each value is flattened to a single
 * string — but **all** messages are kept and joined, not just the first. A
 * password or price field can legitimately carry two complaints at once, and
 * showing only one sends the user round the loop twice.
 *
 * `non_field_errors` / `detail` / `error` are folded into `_general` so a form
 * can show them in a banner. When the body yields nothing usable at all, the
 * caller's `fallback` becomes `_general` — an error response must never render
 * as an empty modal with no explanation of what went wrong.
 */
export function fieldErrors(body, fallback = '') {
  const out = {};

  const flatten = (value) => {
    if (Array.isArray(value)) {
      return value.map(flatten).filter(Boolean).join(' ');
    }
    if (value && typeof value === 'object') {
      return Object.values(value).map(flatten).filter(Boolean).join(' ');
    }
    return value ? String(value) : '';
  };

  const append = (key, message) => {
    if (!message) return;
    out[key] = out[key] ? `${out[key]} ${message}` : message;
  };

  if (body && typeof body === 'object') {
    for (const [key, value] of Object.entries(body)) {
      const message = flatten(value);
      if (!message) continue;
      if (key === 'non_field_errors' || key === 'detail' || key === 'error') {
        append('_general', message);
      } else {
        append(key, message);
      }
    }
  }

  if (Object.keys(out).length === 0 && fallback) out._general = fallback;
  return out;
}
