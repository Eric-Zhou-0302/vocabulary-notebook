'use strict'

function sanitizePreferences(value) {
  const result = {}
  if (!value || typeof value !== 'object' || Array.isArray(value)) return result
  if (['light', 'dark'].includes(value.theme)) result.theme = value.theme
  if (['', 'created_asc', 'created_desc', 'alpha_asc', 'alpha_desc'].includes(value['vocabulary-word-sort'])) {
    result['vocabulary-word-sort'] = value['vocabulary-word-sort']
  }
  return result
}

module.exports = { sanitizePreferences }
