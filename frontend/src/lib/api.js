export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function fetchJson(url, { signal, method = 'GET' } = {}) {
  let response;
  try {
    response = await fetch(url, { signal, method, headers: { Accept: 'application/json' } });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('Server lokal tidak dapat dihubungi. Pastikan Uvicorn masih berjalan.', 0);
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* respons bukan JSON */
    }
    throw new ApiError(detail, response.status);
  }
  return response.json();
}

export const api = {
  tickers: (signal) => fetchJson('/api/tickers', { signal }),
  market: (ticker, start, end, signal) => {
    const params = new URLSearchParams();
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    const query = params.toString();
    return fetchJson(`/api/market/${ticker}${query ? `?${query}` : ''}`, { signal });
  },
  news: (ticker, sessionDate, signal) =>
    fetchJson(`/api/news/${ticker}${sessionDate ? `?session_date=${sessionDate}` : ''}`, { signal }),
  feeds: (signal) => fetchJson('/api/feeds/status', { signal }),
  syncNow: () => fetchJson('/api/feeds/sync', { method: 'POST' }),
  prices: (signal) => fetchJson('/api/prices/status', { signal }),
  syncPrices: () => fetchJson('/api/prices/sync', { method: 'POST' }),
  fundamentals: (ticker, signal, refresh = false) =>
    fetchJson(`/api/fundamentals/${ticker}${refresh ? '?refresh=true' : ''}`, { signal }),
};
