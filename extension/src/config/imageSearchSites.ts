import type { RecommendedSearchSite, SearchPlatformLink } from '../types/search'
import platformConfigs from '../../../shared/platforms.json'

export const imageSearchPlatforms: SearchPlatformLink[] = platformConfigs.filter((item) => item.enabled).map((item) => ({
  platform: item.id, name: item.name, url: item.url_template.replace('{query}', ''), query: '', requiresLogin: item.requires_login,
}))

export function buildPlatformUrl(platform: string, terms: string): string {
  const config = platformConfigs.find((item) => item.id === platform && item.enabled)
  return config ? config.url_template.replace('{query}', encodeURIComponent(terms)) : ''
}

const sites = {
  unsplash: { name: 'Unsplash', url: 'https://unsplash.com/', description: '高质量摄影与氛围图' },
  pexels: { name: 'Pexels', url: 'https://www.pexels.com/', description: '免费摄影与视频素材' },
  pixabay: { name: 'Pixabay', url: 'https://pixabay.com/', description: '图片、插画与矢量素材' },
  freepik: { name: 'Freepik', url: 'https://www.freepik.com/', description: '设计模板、矢量与图标素材' },
  vcg: { name: '视觉中国', url: 'https://www.vcg.com/', description: '商业摄影与本土化内容', requiresLogin: true },
  huaban: { name: '花瓣网', url: 'https://huaban.com/', description: '设计灵感与案例采集', requiresLogin: true },
} satisfies Record<string, RecommendedSearchSite>

const recommendations: Record<string, Array<keyof typeof sites>> = {
  graphic_designer: ['freepik', 'huaban', 'vcg'],
  illustrator: ['freepik', 'huaban', 'pixabay'],
  photographer: ['unsplash', 'pexels', 'vcg'],
  ecommerce_worker: ['freepik', 'vcg', 'pixabay'],
  ui_designer: ['freepik', 'huaban', 'unsplash'],
  default: ['unsplash', 'freepik', 'huaban'],
}

export function getRecommendedSearchSites(persona?: string): RecommendedSearchSite[] {
  return (recommendations[persona || 'default'] || recommendations.default).map((key) => sites[key])
}
