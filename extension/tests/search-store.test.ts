import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSearchStore } from '../src/stores/search'
import type { SearchAssistResponse } from '../src/types/search'

const result: SearchAssistResponse = { original_query: '猫', query: 'cat', suggestions: [{ keyword: 'cat', category: 'subject', selected: true }], platforms: [{ platform: 'mock', name: 'Mock', url: 'https://example.test/cat', query: 'cat' }], provider: 'mock', is_ai_generated: false, degraded: false, messages: [] }

describe('search store', () => {
  beforeEach(() => setActivePinia(createPinia()))
  it('starts empty', () => expect(useSearchStore().$state).toMatchObject({ originalQuery: '', finalQuery: '', suggestions: [], loading: false, error: '' }))
  it('stores successful search and can reset', () => { const store = useSearchStore(); store.start('猫'); store.succeed(result); expect(store.finalQuery).toBe('cat'); expect(store.platforms).toHaveLength(1); store.reset(); expect(store.originalQuery).toBe('') })
  it('stores an error and stops loading', () => { const store = useSearchStore(); store.start('猫'); store.fail('[server] unavailable'); expect(store.error).toContain('server'); expect(store.loading).toBe(false) })
  it('removes a suggestion and synchronizes query and platform link', () => { const store = useSearchStore(); store.succeed({ ...result, query: 'cat warm', suggestions: [{ keyword: 'cat', selected: true }, { keyword: 'warm', selected: true }], platforms: [{ platform: 'mock', name: 'Mock', url: 'https://example.test/cat%20warm', query: 'cat warm' }] }); store.removeSuggestion('warm'); expect(store.suggestions.map((item) => item.keyword)).toEqual(['cat']); expect(store.finalQuery).toBe('cat'); expect(store.platforms[0]).toMatchObject({ query: 'cat', url: 'https://example.test/cat' }) })
  it('keeps the full text while selected keywords form the search query', () => { const store = useSearchStore(); store.succeed({ ...result, query: 'cat warm light', suggestions: [{ keyword: 'cat', selected: true }, { keyword: 'warm light', selected: false }] }); expect(store.finalQuery).toBe('cat warm light'); expect(store.suggestions.filter((item) => item.selected).map((item) => item.keyword)).toEqual(['cat']) })
})
