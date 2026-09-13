import type { CopyrightStatus, RecommendedSearchSite, SearchPlatformLink } from '../types/search'
import catalog from '../../../shared/platforms.json'

type InteractionMode = 'executable_search' | 'recommendation_only' | 'in_site_search'
type PlatformConfig = (typeof catalog.platforms)[number]

export const copyrightLabels: Record<CopyrightStatus, string> = {
  inspiration_only: '不可照搬',
  license_per_item: '部分可商用',
  attribution_required: '部分可商用',
  broad_reuse_license: '可免费商用',
  commercial_license: '部分可商用',
  unknown: '不可商用',
}

export function getCopyrightLabel(status: string | undefined): string {
  return copyrightLabels[(status || 'unknown') as CopyrightStatus]
}

const enabledPlatforms = catalog.platforms.filter((item) => item.enabled)

function getRankedPlatforms(persona?: string): PlatformConfig[] {
  return persona
    ? [...enabledPlatforms].sort((left, right) => {
        const priorities = (item: PlatformConfig) => item.persona_priorities as Record<string, number>
        const leftPriority = priorities(left)[persona] ?? Number.MAX_SAFE_INTEGER
        const rightPriority = priorities(right)[persona] ?? Number.MAX_SAFE_INTEGER
        return leftPriority - rightPriority || left.id.localeCompare(right.id)
      }).slice(0, 7)
    : enabledPlatforms
}

function toPlatformLink(item: PlatformConfig): SearchPlatformLink {
  return {
    platform: item.id,
    name: item.name,
    url: item.url_template?.replace('{query}', '') || item.homepage_url,
    query: '',
    requiresLogin: item.requires_login,
    requires_login: item.requires_login,
    supports_search_url: item.supports_search_url,
    interaction_mode: item.interaction_mode as InteractionMode,
    copyright_status: item.copyright_status as CopyrightStatus,
    copyright_notice: item.copyright_notice,
    recommendation_reason: item.recommendation_reason,
    config_version: item.version,
  }
}

export const imageSearchPlatforms: SearchPlatformLink[] = enabledPlatforms
  .filter((item) => item.supports_search_url && item.url_template)
  .map(toPlatformLink)

export function getRecommendedPlatformLinks(persona?: string): SearchPlatformLink[] {
  return getRankedPlatforms(persona).map(toPlatformLink)
}

export function buildPlatformUrl(platform: string, terms: string): string {
  const config = enabledPlatforms.find((item) => item.id === platform)
  if (!config?.supports_search_url || !config.url_template) return ''
  return config.url_template.replace('{query}', encodeURIComponent(terms))
}

export function getRecommendedSearchSites(persona?: string): RecommendedSearchSite[] {
  return getRankedPlatforms(persona).map((item) => ({
    platform: item.id,
    name: item.name,
    url: item.homepage_url,
    description: item.recommendation_reason,
    requiresLogin: item.requires_login,
    supportsSearchUrl: item.supports_search_url,
    interactionMode: item.interaction_mode as InteractionMode,
    copyrightStatus: item.copyright_status as CopyrightStatus,
    copyrightNotice: item.copyright_notice,
    version: item.version,
  }))
}

export const searchablePlatformOptions = imageSearchPlatforms.map((item) => ({
  label: item.name,
  value: item.platform,
  copyrightStatus: item.copyright_status || 'unknown',
}))

export const platformConfigVersion = catalog.config_version
export const platformOrderReviewStatus = catalog.review_status
