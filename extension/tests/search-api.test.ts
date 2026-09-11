import { afterEach, describe, expect, it, vi } from 'vitest'
import { assistSearch } from '../src/api/search'
import { ApiError } from '../src/api/http'

afterEach(() => vi.restoreAllMocks())
const response = { original_query: '猫', query: 'cat', suggestions: [], platforms: [], provider: 'mock', is_ai_generated: false, degraded: true, messages: [] }

describe('search API mock boundary', () => {
  it('sends basic mode and enabled network expansion by default', async () => { const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(response), { status: 200 })); await expect(assistSearch('猫')).resolves.toEqual(response); expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/v1/search/assist'), expect.objectContaining({ method: 'POST', body: JSON.stringify({ query: '猫', language: 'auto', optimization_mode: 'basic', network_expansion: true }) })) })
  it('sends persona, smart mode, and the user network choice', async () => { const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(response), { status: 200 })); await assistSearch('咖啡店', 'auto', 'graphic_designer', undefined, 'smart', false); expect(fetchMock.mock.calls[0][1]?.body).toBe(JSON.stringify({ query: '咖啡店', language: 'auto', persona: 'graphic_designer', optimization_mode: 'smart', network_expansion: false })) })
  it('classifies backend validation errors without real requests', async () => { vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'query invalid' }), { status: 422 })); await expect(assistSearch('')).rejects.toMatchObject({ category: 'validation', message: 'query invalid' } satisfies Partial<ApiError>) })
  it('classifies network failures', async () => { vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline')); await expect(assistSearch('猫')).rejects.toMatchObject({ category: 'network' }) })
})
