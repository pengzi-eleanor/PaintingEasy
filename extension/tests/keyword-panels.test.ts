import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it } from 'vitest'
import ImageAnalyzePanel from '../src/components/ImageAnalyzePanel.vue'
import KeywordOptimizePanel from '../src/components/KeywordOptimizePanel.vue'
import { getRecommendedSearchSites, imageSearchPlatforms } from '../src/config/imageSearchSites'
import type { SearchPlatformLink, SearchSuggestion } from '../src/types/search'

const suggestions: SearchSuggestion[] = [
  { keyword: 'warm cafe', category: 'scene', selected: true, source: 'mock' },
]
const platforms: SearchPlatformLink[] = [
  { platform: 'unsplash', name: 'Unsplash', url: 'https://example.test/', query: 'warm cafe' },
]
const global = { plugins: [ElementPlus] }

describe('keyword result panels', () => {
  it('renders the text keyword result with only one card container', () => {
    const wrapper = mount(KeywordOptimizePanel, {
      props: { suggestions, platforms, selectedPlatform: 'unsplash', finalQuery: 'warm cafe', error: '', warning: '' },
      global,
    })

    expect(wrapper.findAll('.result-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('关键词建议 · 可编辑')
  })

  it('renders one image analyze action and reuses the same keyword result UI', () => {
    const wrapper = mount(ImageAnalyzePanel, {
      props: { imageName: 'cafe.jpg', imageId: 'image-1', suggestions, platforms, selectedPlatform: 'unsplash', finalQuery: 'warm cafe' },
      global,
    })

    expect(wrapper.text().match(/识别关键词/g)).toHaveLength(1)
    expect(wrapper.findAll('.result-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('关键词建议 · 可编辑')
    expect(wrapper.text()).toContain('搜索所选关键词')
  })

  it('offers additional image platforms and marks sites that require login', () => {
    const wrapper = mount(ImageAnalyzePanel, {
      props: { imageName: 'cafe.jpg', suggestions, platforms: imageSearchPlatforms, selectedPlatform: 'unsplash', finalQuery: 'warm cafe', persona: 'photographer' },
      global,
    })

    expect(imageSearchPlatforms.map((item) => item.name)).toEqual(['Unsplash', 'Pexels', 'Pixabay', 'Freepik', '视觉中国', '花瓣网'])
    expect(wrapper.findAll('.platform-option')).toHaveLength(6)
    expect(wrapper.findAll('.login-badge')).toHaveLength(2)
    expect(wrapper.text()).toContain('根据您的职业推荐')
    expect(wrapper.find('.recommended-sites').text()).toContain('Pexels')
  })

  it('returns different recommended sites for different professions', () => {
    expect(getRecommendedSearchSites('illustrator').map((item) => item.name)).toEqual(['Freepik', '花瓣网', 'Pixabay'])
    expect(getRecommendedSearchSites('photographer').map((item) => item.name)).toEqual(['Unsplash', 'Pexels', '视觉中国'])
  })
})
