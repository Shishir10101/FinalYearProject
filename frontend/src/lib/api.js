const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

class ApiClient {
  constructor() {
    this.baseUrl = API_URL;
  }

  getToken() {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('access_token');
    }
    return null;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const token = this.getToken();
    
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (response.status === 401) {
        // Try to refresh token
        const refreshed = await this.refreshToken();
        if (refreshed) {
          headers['Authorization'] = `Bearer ${this.getToken()}`;
          const retryResponse = await fetch(url, { ...options, headers });
          if (!retryResponse.ok) {
            const error = await retryResponse.json().catch(() => ({}));
            throw new Error(error.detail || `Request failed: ${retryResponse.status}`);
          }
          return retryResponse.json();
        } else {
          if (typeof window !== 'undefined') {
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
          }
          throw new Error('Session expired. Please login again.');
        }
      }

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        const thrown = new Error(
          error.detail || error.error || JSON.stringify(error) || `Request failed: ${response.status}`
        );
        // Attach the raw DRF payload and status so a form can show per-field
        // messages. Additive: the message string above is unchanged, so existing
        // callers that only read `.message` behave exactly as before.
        thrown.fields = error;
        thrown.status = response.status;
        throw thrown;
      }

      if (response.status === 204) return null;
      return response.json();
    } catch (error) {
      console.error('API Error:', error);
      throw error;
    }
  }

  async refreshToken() {
    const refresh = typeof window !== 'undefined' ? localStorage.getItem('refresh_token') : null;
    if (!refresh) return false;

    try {
      const response = await fetch(`${this.baseUrl}/auth/token/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
      });

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('access_token', data.access);
        if (data.refresh) localStorage.setItem('refresh_token', data.refresh);
        return true;
      }
    } catch (e) {
      console.error('Token refresh failed:', e);
    }
    return false;
  }

  get(endpoint) {
    return this.request(endpoint);
  }

  post(endpoint, data) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  put(endpoint, data) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  patch(endpoint, data) {
    return this.request(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  }
}

const api = new ApiClient();

// Auth
export const authAPI = {
  register: (data) => api.post('/auth/register/', data),
  login: (data) => api.post('/auth/login/', data),
  getProfile: () => api.get('/auth/profile/'),
  updateProfile: (data) => api.put('/auth/profile/', data),
  // Always resolves with a generic message, whether or not the email is
  // registered — the backend refuses to reveal which addresses have accounts.
  requestPasswordReset: (email) => api.post('/auth/password-reset/', { email }),
  confirmPasswordReset: (data) => api.post('/auth/password-reset/confirm/', data),
  // Authenticated change, distinct from the reset above: needs the current
  // password, does not need the mailbox. The server revokes every token on
  // success — including this session's — so the caller must sign out locally
  // rather than keep using a token that is now dead.
  changePassword: (data) => api.post('/auth/password-change/', data),
  // "Sign out everywhere". The endpoint has existed since Day 7 and no client
  // called it, so the remedy it documents was unreachable from the product.
  logoutAll: () => api.post('/auth/logout-all/', {}),
};

// Products
export const productsAPI = {
  list: (params = '') => api.get(`/products/${params ? '?' + params : ''}`),
  // Domain-aware search. Unlike `?search=` on the list endpoint this ranks by
  // relevance, resolves alternative spellings of a Nepali term ("sindur" finds
  // "Sindoor"), and reaches the samagri behind a ritual or festival name. Every
  // result carries a `match` block saying why it is there.
  search: ({ q, category = '', page = 1 }) => {
    const params = new URLSearchParams({ q, page: String(page) });
    if (category) params.append('category', category);
    return api.get(`/products/search/?${params.toString()}`);
  },
  detail: (slug) => api.get(`/products/${slug}/`),
  featured: () => api.get('/products/featured/'),
  categories: () => api.get('/products/categories/'),
  byCategory: (slug, params = '') => api.get(`/products/categories/${slug}/${params ? '?' + params : ''}`),
  // Delivery areas come from the server so an area added in the admin dashboard
  // shows up here without a code change.
  areas: () => api.get('/products/areas/'),
  // Reviews. One call returns the summary, the page of reviews, the total and the
  // signed-in reader's own review, because the product page renders all four.
  reviews: (slug, page = 1) => api.get(`/products/${slug}/reviews/?page=${page}`),
  // POST is create-or-update: the API enforces one review per customer per product,
  // so a second post is an edit of your own rather than a duplicate.
  submitReview: (slug, data) => api.post(`/products/${slug}/reviews/`, data),
  deleteReview: (id) => api.delete(`/products/reviews/${id}/`),
};

// Wishlist
export const wishlistAPI = {
  // Returns a **bare array** (unpaginated) of `{ id, product, created_at }`, newest
  // first — the API deliberately does not wrap it in `results`, so do not reach for
  // `.results` here.
  list: () => api.get('/products/wishlist/'),
  // Adding is idempotent (create-or-get): a second add returns 200 with the existing
  // row rather than 400, so a double-clicked heart is harmless.
  add: (productId) => api.post('/products/wishlist/', { product_id: productId }),
  // Keyed by product id, not by the wishlist row id: the heart lives on a product
  // card, which knows the product and not the saved row.
  remove: (productId) => api.delete(`/products/wishlist/${productId}/`),
};

// Festivals
export const festivalsAPI = {
  kits: (festivalType = '') => api.get(`/festivals/kits/${festivalType ? '?festival_type=' + festivalType : ''}`),
  kitDetail: (id) => api.get(`/festivals/kits/${id}/`),
  upcoming: (limit) => api.get(`/festivals/upcoming/${limit ? '?limit=' + limit : ''}`),
  // Rituals. A separate entry point from kits: a puja can exist before anyone
  // has assembled a kit for it, which is the normal state of affairs.
  pujas: () => api.get('/festivals/pujas/'),
  pujaDetail: (slug) => api.get(`/festivals/pujas/${slug}/`),
  recommendations: () => api.get('/festivals/recommendations/'),
};

// Cart
export const cartAPI = {
  get: () => api.get('/orders/cart/'),
  add: (productId, quantity = 1) => api.post('/orders/cart/add/', { product_id: productId, quantity }),
  update: (cartItemId, quantity) => api.put(`/orders/cart/update/${cartItemId}/`, { quantity }),
  remove: (cartItemId) => api.delete(`/orders/cart/remove/${cartItemId}/`),
  addKit: (kitId) => api.post(`/orders/cart/add-kit/${kitId}/`),
  // Adds only the items the ritual marks as required, and reports anything it
  // had to skip because it is out of stock.
  addPuja: (pujaId) => api.post(`/orders/cart/add-puja/${pujaId}/`),
};

// Orders
export const ordersAPI = {
  config: () => api.get('/orders/config/'),
  checkout: (data) => api.post('/orders/checkout/', data),
  list: () => api.get('/orders/'),
  // The orders endpoint is paginated at PAGE_SIZE = 12. `/account` only ever shows
  // the five most recent, so the full history needs to walk the pages — a list that
  // silently stopped at the first page would be the same class of bug as the
  // paginated item lists in the admin dashboard.
  listPage: (page = 1) => api.get(`/orders/?page=${page}`),
  detail: (id) => api.get(`/orders/${id}/`),
};

export default api;
