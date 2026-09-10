import { defineStore } from "pinia";
import type { SearchAssistResponse, SearchSuggestion } from "../types/search";
import { buildPlatformUrl } from "../config/imageSearchSites";

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
      this.loading = false;
    },
    removeSuggestion(id: string) {
      this.suggestions = this.suggestions.filter((item) => item.id !== id);
      this.finalQuery = this.suggestions.map((item) => item.keyword).join(" ");
      this.platforms = this.platforms.map((platform) => {
        return {
          ...platform,
          query: this.finalQuery,
          url: buildPlatformUrl(platform.platform, this.finalQuery),
        };
      });
    },
    fail(message: string) {
      this.error = message;
      this.loading = false;
    },
    reset() {
      this.$reset();
    },
  },
});
