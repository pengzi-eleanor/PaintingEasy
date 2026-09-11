import { defineStore } from "pinia";
import type {
  OptimizationMode,
  SearchAssistResponse,
  SearchSuggestion,
} from "../types/search";
import { buildPlatformUrl } from "../config/imageSearchSites";

const NETWORK_SETTING_KEY = "painting-easy-network-expansion";
const NETWORK_NOTICE_KEY = "painting-easy-network-notice";

function storedBoolean(key: string, fallback: boolean): boolean {
  const value = globalThis.localStorage?.getItem(key);
  return value == null ? fallback : value === "true";
}

export const useSearchStore = defineStore("search", {
  state: () => ({
    originalQuery: "",
    finalQuery: "",
    suggestions: [] as SearchSuggestion[],
    platforms: [] as SearchAssistResponse["platforms"],
    loading: false,
    selectedPlatform: "",
    error: "",
    warning: "",
    persona: "",
    optimizationMode: "" as OptimizationMode | "",
    generationStatus: null as SearchAssistResponse["generation_status"] | null,
    networkExpansionEnabled: storedBoolean(NETWORK_SETTING_KEY, true),
    networkNoticeAcknowledged: storedBoolean(NETWORK_NOTICE_KEY, false),
  }),
  actions: {
    start(query: string) {
      this.originalQuery = query;
      this.finalQuery = query;
      this.loading = true;
      this.error = "";
      this.warning = "";
    },
    succeed(result: SearchAssistResponse) {
      this.originalQuery = result.original_query;
      this.finalQuery = result.query;
      this.suggestions = result.suggestions;
      this.platforms = result.platforms;
      this.selectedPlatform = result.platforms[0]?.platform ?? "";
      this.warning = result.messages.join("；");
      this.optimizationMode = result.optimization_mode;
      this.generationStatus = result.generation_status;
      this.loading = false;
    },
    removeSuggestion(id: string) {
      this.suggestions = this.suggestions.filter(
        (item) => (item.id ?? item.keyword) !== id,
      );
      this.finalQuery = this.suggestions.map((item) => item.keyword).join(" ");
      this.platforms = this.platforms.map((platform) => {
        const configuredUrl = buildPlatformUrl(platform.platform, this.finalQuery);
        return {
          ...platform,
          query: this.finalQuery,
          url:
            configuredUrl ||
            platform.url.replace(
              encodeURIComponent(platform.query),
              encodeURIComponent(this.finalQuery),
            ),
        };
      });
    },
    fail(message: string) {
      this.error = message;
      this.loading = false;
    },
    setNetworkExpansion(value: boolean) {
      this.networkExpansionEnabled = value;
      globalThis.localStorage?.setItem(NETWORK_SETTING_KEY, String(value));
    },
    acknowledgeNetworkNotice() {
      this.networkNoticeAcknowledged = true;
      globalThis.localStorage?.setItem(NETWORK_NOTICE_KEY, "true");
    },
    reset() {
      this.$reset();
    },
  },
});
