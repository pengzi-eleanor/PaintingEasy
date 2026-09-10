<script setup lang="ts">
import type { SearchPlatformLink, SearchSuggestion } from "../types/search";
defineProps<{
  suggestions: SearchSuggestion[];
  platforms: SearchPlatformLink[];
  finalQuery: string;
  selectedPlatform: string;
}>();
const emit = defineEmits<{
  remove: [id: string];
  "update:finalQuery": [value: string];
  selectPlatform: [platform: string];
  search: [];
}>();
</script>
<template>
  <div v-if="suggestions.length" class="keyword-selection result-card">
    <div class="query-tools">
      <el-input
        :model-value="finalQuery"
        aria-label="完整关键词"
        @update:model-value="emit('update:finalQuery', $event)"
      />
    </div>
    <div class="result-title">
      <span>关键词建议 · 可编辑</span><small>Mock</small>
    </div>
    <div class="keyword-tabs" role="tablist">
      <div
        v-for="item in suggestions"
        :key="item.id || item.keyword"
        class="keyword-tab"
        role="tab"
        :title="item.reason"
      >
        <el-checkbox v-model="item.selected">{{
          item.display_keyword || item.keyword
        }}</el-checkbox
        ><button
          type="button"
          class="keyword-close"
          :disabled="item.removable === false"
          @click="emit('remove', item.id || item.keyword)"
        >
          ×</button
        ><small>{{ item.group || "core" }} · {{ item.category }}</small>
      </div>
    </div>
    <div class="result-title"><span>选择素材平台（单选）</span></div>
    <div class="platforms">
      <label
        v-for="platform in platforms"
        :key="platform.platform"
        class="platform-option"
        ><input
          type="radio"
          name="search-platform"
          :checked="selectedPlatform === platform.platform"
          @change="emit('selectPlatform', platform.platform)"
        /><span>{{ platform.name }}</span
        ><small v-if="platform.requiresLogin" class="login-badge"
          >需登录</small
        ></label
      >
    </div>
    <el-button
      class="search-button"
      type="primary"
      :disabled="
        !suggestions.some((item) => item.selected) || !selectedPlatform
      "
      @click="emit('search')"
      >搜索所选关键词</el-button
    >
  </div>
</template>
