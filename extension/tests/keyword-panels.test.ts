import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import App from '../src/App.vue'
import ImageAnalyzePanel from '../src/components/ImageAnalyzePanel.vue'
import KeywordOptimizePanel from '../src/components/KeywordOptimizePanel.vue'
import PlatformGuidePanel from '../src/components/PlatformGuidePanel.vue'
import SettingsPanel from '../src/components/SettingsPanel.vue'
import { getCopyrightLabel, getRecommendedPlatformLinks, getRecommendedSearchSites, imageSearchPlatforms } from '../src/config/imageSearchSites'
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

  it('uses the shared platform result UI without a duplicate recommendation list', () => {
    const recommendedPlatforms = getRecommendedPlatformLinks('photographer')
    const wrapper = mount(ImageAnalyzePanel, {
      props: { imageName: 'cafe.jpg', suggestions, platforms: recommendedPlatforms, selectedPlatform: 'unsplash', finalQuery: 'warm cafe', persona: 'photographer' },
      global,
    })

    expect(imageSearchPlatforms.map((item) => item.name)).toContain('Figma Community')
    expect(imageSearchPlatforms.map((item) => item.name)).not.toContain('小红书')
    expect(recommendedPlatforms.map((item) => item.name)).toEqual(['Unsplash', 'Pexels', '视觉中国', 'Pixabay', 'Pinterest', '小红书', 'ArtStation'])
    expect(wrapper.findAll('.platform-option')).toHaveLength(recommendedPlatforms.length)
    expect(wrapper.find('.recommended-sites').exists()).toBe(false)
  })

  it('returns different recommended sites for different professions', () => {
    expect(getRecommendedSearchSites('illustrator').map((item) => item.name)).toEqual(['Pinterest', '小红书', 'Pixiv', 'ArtStation', 'Behance', '花瓣网', 'Freepik'])
    expect(getRecommendedSearchSites('photographer').map((item) => item.name)).toEqual(['Unsplash', 'Pexels', '视觉中国', 'Pixabay', 'Pinterest', '小红书', 'ArtStation'])
  })

  it('shows copyright labels and in-site operation status without a fake search URL', () => {
    const sites = getRecommendedSearchSites('graphic_designer')
    const recommendedPlatforms = getRecommendedPlatformLinks('graphic_designer')
    expect(sites.find((item) => item.name === '小红书')).toMatchObject({ supportsSearchUrl: false, interactionMode: 'in_site_search', url: 'https://www.xiaohongshu.com/' })
    const wrapper = mount(ImageAnalyzePanel, {
      props: { imageName: 'cafe.jpg', suggestions, platforms: recommendedPlatforms, selectedPlatform: 'xiaohongshu', finalQuery: 'warm cafe', persona: 'graphic_designer' }, global,
    })
    expect(wrapper.text()).toContain('不可照搬')
    expect(wrapper.text()).toContain('打开平台后站内搜索')
  })

  it('uses only the four explicit commercial-use labels', () => {
    expect(getCopyrightLabel('broad_reuse_license')).toBe('可免费商用')
    expect(getCopyrightLabel('inspiration_only')).toBe('不可照搬')
    expect(getCopyrightLabel('license_per_item')).toBe('部分可商用')
    expect(getCopyrightLabel('unknown')).toBe('不可商用')
  })

  it('explains that Tencent keyword expansion runs locally', () => {
    const wrapper = mount(SettingsPanel, {
      props: { modelValue: 'unsplash' },
      global,
    })
    expect(wrapper.text()).toContain('腾讯中文词向量在本地运行')
    expect(wrapper.text()).not.toContain('Wikidata')
  })

  it('keeps platform introductions separate from settings without an inner scroller', () => {
    const wrapper = mount(PlatformGuidePanel, { global })

    expect(wrapper.text()).toContain('素材平台介绍')
    expect(wrapper.text()).not.toContain('搜索设置')
    expect(wrapper.find('.settings').exists()).toBe(false)
    expect(wrapper.find('.platform-guide-list').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('https://')
    expect(wrapper.findAll('.platform-guide-item').every((item) => item.attributes('href'))).toBe(true)
  })

  it('opens settings as a standalone view outside the main tabs', async () => {
    const wrapper = mount(App, {
      global: { plugins: [ElementPlus, createPinia()] },
    })

    await wrapper.find('.brand-guide-button').trigger('click')

    expect(wrapper.find('.settings').exists()).toBe(true)
    expect(wrapper.find('.main-tabs').exists()).toBe(false)
    expect(wrapper.find('.brand-guide-button').text()).toContain('返回')
  })
})
