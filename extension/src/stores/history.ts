import { defineStore } from "pinia";
import type { SearchHistoryItem } from "../types/search";

export const useHistoryStore = defineStore("history", {
  state: () => ({ items: [] as SearchHistoryItem[] }),
  actions: {
    add(query: string, keywords: string[]) {
      this.items.unshift({
        id: Date.now(),
        query,
        keywords,
        createdAt: new Date().toLocaleString(),
      });
      this.items = this.items.slice(0, 20);
    },
    clear() {
      this.items = [];
    },
  },
});
