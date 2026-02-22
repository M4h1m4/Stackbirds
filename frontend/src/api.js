/**
 * Client for the invoice processor API. No upload — input is from email (IMAP).
 * Base URL: VITE_API_URL or http://localhost:8000. When empty (Docker/same-origin), API is at /api.
 */
const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const API_BASE = (BASE_URL && BASE_URL.length > 0) ? BASE_URL : '/api';

async function request(path, options = {}) {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = new Error(res.statusText || `HTTP ${res.status}`);
    err.status = res.status;
    try {
      err.body = await res.json();
    } catch {
      err.body = { detail: await res.text() };
    }
    throw err;
  }
  const contentType = res.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return res.json();
  }
  return res.text();
}

/**
 * GET /processing. Use inbox_email for "my inbox" (processings created from that inbox), or customer_id for sender.
 * @param {string} email - Inbox email (e.g. your email that receives invoices) or customer_id
 * @param {{ byInbox?: boolean }} [opts] - If byInbox true, use inbox_email param (default: true for client flow)
 * @returns {Promise<Array<{ processing_id: string, invoice_id: string, customer_id: string, user_visible_phase: string, states: Array }>>}
 */
export function getProcessingList(email, opts = {}) {
  const byInbox = opts.byInbox !== false;
  const param = byInbox ? 'inbox_email' : 'customer_id';
  return request(`/processing?${param}=${encodeURIComponent(email)}`);
}

/**
 * GET /extraction?state_id=...
 */
export function getExtraction(stateId) {
  return request(`/extraction?state_id=${encodeURIComponent(stateId)}`);
}

/**
 * GET /matching?state_id=...
 */
export function getMatching(stateId) {
  return request(`/matching?state_id=${encodeURIComponent(stateId)}`);
}

/**
 * GET /clarification?clarification_id=...
 */
export function getClarification(clarificationId) {
  return request(`/clarification?clarification_id=${encodeURIComponent(clarificationId)}`);
}

/**
 * POST /clarification?clarification_id=... with body { answers, completed }
 */
export function submitClarification(clarificationId, body) {
  return request(
    `/clarification?clarification_id=${encodeURIComponent(clarificationId)}`,
    { method: 'POST', body: JSON.stringify(body) }
  );
}

/**
 * GET /completion?processing_id=... (when user_visible_phase === 'Completion')
 */
export function getCompletion(processingId) {
  return request(`/completion?processing_id=${encodeURIComponent(processingId)}`);
}

/**
 * GET /health
 */
export function getHealth() {
  return request('/health');
}
