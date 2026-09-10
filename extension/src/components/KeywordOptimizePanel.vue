<script setup lang="ts">
import KeywordSelectionPanel from "./KeywordSelectionPanel.vue";
import type { SearchPlatformLink, SearchSuggestion } from "../types/search";

defineProps<{
  suggestions: SearchSuggestion[];
  platforms: SearchPlatformLink[];
  error: string;
  warning: string;
  finalQuery: string;
  selectedPlatform: string;
}>();
const emit = defineEmits<{
  retry: [];
  remove: [keyword: string];
  "update:finalQuery": [value: string];
  selectPlatform: [platform: string];
  search: [];
}>();
</script>

<template>
  <section class="panel">
    <slot name="input" />
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
    />
    <el-alert
      v-else-if="warning"
      :title="warning"
      type="warning"
      show-icon
      :closable="false"
    />
    <KeywordSelectionPanel
      v-if="suggestions.length"
      :suggestions="suggestions"
      :platforms="platforms"
      :selected-platform="selectedPlatform"
      :final-query="finalQuery"
      @remove="(keyword) => emit('remove', keyword)"
      @select-platform="(platform) => emit('selectPlatform', platform)"
      @search="emit('search')"
      @update:final-query="(value) => emit('update:finalQuery', value)"
    />
    <el-empty v-else description="输入描述后生成可选搜索词" :image-size="72" />
    <el-button v-if="error" text type="primary" @click="emit('retry')"
      >重试</el-button
    >
  </section>
</template>
