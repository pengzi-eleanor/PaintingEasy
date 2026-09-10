import type { SearchSuggestion } from './types/search'

const dictionary: Record<string, string[]> = {
  咖啡: ['coffee', 'coffee shop', 'warm light', 'lifestyle photography'],
  海报: ['poster design', 'graphic layout', 'editorial', 'typography'],
  科技: ['technology', 'futuristic', 'blue gradient', '3d render'],
  人物: ['portrait', 'people', 'natural pose', 'studio lighting'],
}

export function mockOptimize(query: string): SearchSuggestion[] {
  const normalized = query.trim()
  if (!normalized) return []

  const matched = Object.entries(dictionary)
    .filter(([key]) => normalized.includes(key))
    .flatMap(([, words]) => words)
  const fallbacks = ['creative asset', 'high quality', 'commercial use']

  return [...new Set(matched.length ? matched : [normalized, ...fallbacks])].map((keyword) => ({
    keyword,
    selected: true,
  }))
}

export const mockImageKeywords = ['minimal workspace', 'laptop', 'desk', 'natural light', 'top view']
