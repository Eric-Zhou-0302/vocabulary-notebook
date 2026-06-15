const BASE = '/api'

async function request(url, options = {}) {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const error = new Error(err.detail || '请求失败')
    error.status = res.status
    throw error
  }
  return res
}

export async function fetchWords({ q = '', date = '', page = 1, size = 20, sort = '', letter = '' } = {}) {
  const params = new URLSearchParams({ q, date, page, size, sort, letter })
  const res = await request(`/words?${params}`)
  return res.json()
}

export async function fetchDates() {
  const res = await request('/dates')
  return res.json()
}

export async function fetchWord(id) {
  const res = await request(`/words/${id}`)
  return res.json()
}

export async function createWord(word, definition = '') {
  const res = await request('/words', {
    method: 'POST',
    body: JSON.stringify({ word, definition }),
  })
  return res.json()
}

export async function updateWord(id, data) {
  const res = await request(`/words/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function deleteWord(id) {
  await request(`/words/${id}`, { method: 'DELETE' })
}

export function exportUrl(format, { q = '', date = '', sort = '' } = {}) {
  const params = new URLSearchParams({ format, q, date, sort })
  return `${BASE}/words/export?${params}`
}

export async function enrichMissing() {
  const res = await request('/words/enrich-missing', { method: 'POST' })
  return res.json()
}
