import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it } from 'vitest'
import ImageAnalyzePanel from '../src/components/ImageAnalyzePanel.vue'
import KeywordOptimizePanel from '../src/components/KeywordOptimizePanel.vue'
import SettingsPanel from '../src/components/SettingsPanel.vue'
import { getRecommendedSearchSites, imageSearchPlatforms } from '../src/config/imageSearchSites'
import type { SearchPlatformLink, SearchSuggestion } from '../src/types/search'

const suggestions: SearchSuggestion[] = [
  { keyword: 'warm cafe', category: 'scene', selected: true, source: 'mock' },
]
const platforms: SearchPlatformLink[] = [
  { platform: 'unsplash', name: 'Unsplash', url: 'https://example.test/', query: 'warm cafe', copyright_status: 'broad_reuse_license', copyright_notice: '逐项核对许可' },
]
const global = { plugins: [ElementPlus] }

describe('keyword result panels', () => {
  it('renders the text keyword result with only one card container', () => {
    const wrapper = mount(KeywordOptimizePanel, {
      props: { suggestions, platforms, selectedPlatform: 'unsplash', finalQuery: 'warm cafe', error: '', warning: '' },
      global,
    })

    expect(wrapper.findAll('.result-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('结果关键词')
    expect(wrapper.text()).toContain('可多选，点击切换')
    expect(wrapper.text()).toContain('核心词 · 场景')
    expect(wrapper.text()).not.toContain('模拟建议')
    expect(wrapper.findAll('.el-checkbox')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('core · scene')
    expect(wrapper.findAll('.platform-option')).toHaveLength(1)
    expect(wrapper.find('.platform-copy').text()).toContain('可直接搜索')
  })

  it('renders one image analyze action and reuses the same keyword result UI', () => {
    const wrapper = mount(ImageAnalyzePanel, {
      props: { imageName: 'cafe.jpg', imageId: 'image-1', suggestions, platforms, selectedPlatform: 'unsplash', finalQuery: 'warm cafe' },
      global,
    })

    expect(wrapper.text().match(/识别关键词/g)).toHaveLength(1)
    expect(wrapper.findAll('.result-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('结果关键词')
    expect(wrapper.text()).toContain('搜索所选关键词')
  })

  it('offers additional image platforms and marks sites that require login', () => {
    const wrapper = mount(ImageAnalyzePanel, {
      props: { imageName: 'cafe.jpg', suggestions, platforms: imageSearchPlatforms, selectedPlatform: 'unsplash', finalQuery: 'warm cafe', persona: 'photographer' },
      global,
    })

    expect(imageSearchPlatforms.map((item) => item.name)).toContain('Figma Community')
    expect(imageSearchPlatforms.map((item) => item.name)).not.toContain('小红书')
    expect(wrapper.findAll('.platform-option')).toHaveLength(imageSearchPlatforms.length)
    expect(wrapper.findAll('.login-badge').length).toBeGreaterThan(2)
    expect(wrapper.text()).toContain('根据您的职业推荐')
    expect(wrapper.find('.recommended-sites').text()).toContain('Pexels')
  })

  it('returns different recommended sites for different professions', () => {
    expect(getRecommendedSearchSites('illustrator').map((item) => item.name)).toEqual(['Pinterest', 'Pixiv', 'ArtStation', 'Behance', '花瓣网', 'Freepik', '小红书'])
    expect(getRecommendedSearchSites('photographer').map((item) => item.name)).toEqual(['Unsplash', 'Pexels', '视觉中国', 'Pixabay', 'Pinterest', '小红书'])
  })

  it('shows copyright labels and in-site operation status without a fake search URL', () => {
    const sites = getRecommendedSearchSites('graphic_designer')
    expect(sites.find((item) => item.name === '小红书')).toMatchObject({ supportsSearchUrl: false, interactionMode: 'in_site_search', url: 'https://www.xiaohongshu.com/' })
    const wrapper = mount(ImageAnalyzePanel, {
      props: { imageName: 'cafe.jpg', suggestions, platforms, selectedPlatform: 'unsplash', finalQuery: 'warm cafe', persona: 'graphic_designer' }, global,
    })
    expect(wrapper.text()).toContain('仅供灵感')
    expect(wrapper.text()).toContain('站内操作')
  })

  it('explains public queries and lets the user disable network expansion', async () => {
    const wrapper = mount(SettingsPanel, {
      props: { modelValue: 'unsplash', networkExpansion: true },
      global,
    })
    expect(wrapper.text()).toContain('腾讯词向量始终在本地运行')
    const switchComponent = wrapper.findComponent({ name: 'ElSwitch' })
    await switchComponent.vm.$emit('update:modelValue', false)
    expect(wrapper.emitted('update:networkExpansion')?.[0]).toEqual([false])
  })
})
