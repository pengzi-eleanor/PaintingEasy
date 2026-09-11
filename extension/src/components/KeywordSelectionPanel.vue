<script setup lang="ts">
import type { SearchPlatformLink, SearchSuggestion } from "../types/search";
const copyrightLabels: Record<string, string> = {
  inspiration_only: "仅供灵感",
  license_per_item: "逐项核对许可",
  attribution_required: "需要署名",
  broad_reuse_license: "宽松许可",
  commercial_license: "商业许可",
  unknown: "许可未知",
};
const groupLabels: Record<string, string> = {
  core: "核心词",
  expanded: "联想词",
  platform_specific: "平台词",
  negative: "排除词",
};
const categoryLabels: Record<string, string> = {
  subject: "主体",
  scene: "场景",
  style: "风格",
  color: "色彩",
  composition: "构图",
  quality: "品质",
  quality_modifier: "品质",
  general: "通用",
};
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
      <span>结果关键词</span><small>可多选，点击切换</small>
    </div>
    <div class="keyword-tabs" role="list">
      <div
        v-for="item in suggestions"
        :key="item.id || item.keyword"
        class="keyword-tab"
        role="listitem"
      >
        <button
          type="button"
          class="keyword-select"
          :class="{ selected: item.selected }"
          :aria-pressed="item.selected"
          @click="item.selected = !item.selected"
        >{{ item.display_keyword || item.keyword }}</button
        ><button
          type="button"
          class="keyword-close"
          :disabled="item.removable === false"
          @click="emit('remove', item.id || item.keyword)"
        >
          ×</button
        ><small class="keyword-meta"
          >{{ groupLabels[item.group || "core"] || "关键词" }} ·
          {{ categoryLabels[item.category || "general"] || "通用" }}</small>
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
        /><span class="platform-copy"
          ><strong>{{ platform.name }}</strong
          ><small>{{ platform.supports_search_url === false ? "打开平台后站内搜索" : "可直接搜索" }}</small></span
        ><small
          class="copyright-badge"
          :title="`${platform.copyright_notice || '请逐项核对原始许可'}；不构成法律保证`"
          >{{ copyrightLabels[platform.copyright_status || "unknown"] }}</small
        ><small v-if="platform.requires_login || platform.requiresLogin" class="login-badge"
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
