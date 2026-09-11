export interface ScoreBreakdown {
  exact_match: number;
  semantic_similarity: number;
  relation_weight: number;
  persona_weight: number;
  platform_weight: number;
  final_score: number;
}
export interface SearchSuggestion {
  id?: string;
  concept_id?: string;
  display_keyword?: string;
  language?: "zh" | "en" | "mixed" | "auto";
  group?: "core" | "expanded" | "platform_specific";
  removable?: boolean;
  scores?: ScoreBreakdown;
  derived_from?: string[];
  applicable_platforms?: string[];
  keyword: string;
  category?: string;
  selected: boolean;
  source?:
    | "original"
    | "dictionary"
    | "rule"
    | "embedding"
    | "llm"
    | "fallback"
    | "mock";
  reason?: string;
}
export interface ImageUploadResponse {
  image_id: string;
  filename: string;
  content_type: string;
  size: number;
  width: number;
  height: number;
  url: string;
  created_at: string;
  expires_at: string;
  messages: string[];
}
export interface ImageAnalyzeResponse {
  image_id: string;
  provider: "mock" | "vision";
  is_ai_generated: boolean;
  degraded: boolean;
  suggestions: SearchSuggestion[];
  messages: string[];
}

export interface SearchPlatformLink {
  platform: string;
  name: string;
  url: string;
  query: string;
  requiresLogin?: boolean;
  requires_login?: boolean;
  supports_search_url?: boolean;
  interaction_mode?: "executable_search" | "recommendation_only" | "in_site_search";
  copyright_status?: CopyrightStatus;
  copyright_notice?: string;
  recommendation_reason?: string;
  config_version?: string;
  terms?: string[];
  core_term_ids?: string[];
  expanded_term_ids?: string[];
  platform_term_ids?: string[];
  score?: number;
  reasons?: string[];
}

export interface RecommendedSearchSite {
  platform: string;
  name: string;
  url: string;
  description: string;
  requiresLogin?: boolean;
  supportsSearchUrl: boolean;
  interactionMode: "executable_search" | "recommendation_only" | "in_site_search";
  copyrightStatus: CopyrightStatus;
  copyrightNotice: string;
  version: string;
}

export type CopyrightStatus =
  | "inspiration_only"
  | "license_per_item"
  | "attribution_required"
  | "broad_reuse_license"
  | "commercial_license"
  | "unknown";

export interface SearchAssistResponse {
  original_query: string;
  query: string;
  suggestions: SearchSuggestion[];
  platforms: SearchPlatformLink[];
  provider: "mock";
  is_ai_generated: boolean;
  degraded: boolean;
  messages: string[];
  core_terms?: SearchSuggestion[];
  expanded_terms?: SearchSuggestion[];
  platform_terms?: SearchSuggestion[];
  default_query?: string;
  platform_queries?: SearchPlatformLink[];
  retrieval?: {
    strategy: "rules_only" | "hybrid" | "fallback";
    embedding_enabled: boolean;
    embedding_provider: string;
    embedding_model: string;
    knowledge_base_version: string;
    candidate_count: number;
    degraded: boolean;
  };
  warnings?: string[];
  optimization_mode: OptimizationMode;
  knowledge_sources: KnowledgeSourceStatus[];
  platform_recommendations: PlatformRecommendation[];
  generation_status: GenerationStatus;
  core_intent_category?: "subject" | "scene" | "style" | "color" | "composition" | "general";
  uncertainties?: string[];
}

export type OptimizationMode = "basic" | "smart";
export interface KnowledgeSourceStatus {
  source: "local_rules" | "wikidata" | "conceptnet" | "tencent_word2vec";
  status: "available" | "disabled" | "unavailable";
  message: string;
}
export interface PlatformRecommendation {
  platform: string;
  name: string;
  rank: number;
  reason: string;
  homepage_url?: string;
  supports_search_url?: boolean;
  interaction_mode?: "executable_search" | "recommendation_only" | "in_site_search";
  requires_login?: boolean;
  copyright_status?: CopyrightStatus;
  copyright_notice?: string;
  config_version?: string;
}
export interface GenerationStatus {
  status: "not_requested" | "not_available" | "generated" | "fallback";
  ai_used: boolean;
  message: string;
  remaining_uses?: number | null;
}

export interface SearchHistoryItem {
  id: number;
  query: string;
  keywords: string[];
  createdAt: string;
}
