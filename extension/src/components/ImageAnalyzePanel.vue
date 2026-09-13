<script setup lang="ts">
import { Picture } from "@element-plus/icons-vue";
import KeywordSelectionPanel from "./KeywordSelectionPanel.vue";
import { computed, ref } from "vue";
import { getRecommendedPlatformLinks } from "../config/imageSearchSites";
import type { SearchPlatformLink, SearchSuggestion } from "../types/search";
const props = defineProps<{
  imageName: string;
  suggestions: SearchSuggestion[];
  platforms: SearchPlatformLink[];
  finalQuery: string;
  selectedPlatform: string;
  persona?: string;
  previewUrl?: string;
  loading?: boolean;
  analyzing?: boolean;
  error?: string;
  imageId?: string;
}>();
const emit = defineEmits<{
  select: [event: Event];
  analyze: [];
  delete: [];
  remove: [keyword: string];
  "update:finalQuery": [value: string];
  selectPlatform: [platform: string];
  "update:persona": [value: string];
  search: [];
}>();
const previewOpen = ref(false);
const displayedPlatforms = computed(() =>
  getRecommendedPlatformLinks(props.persona).slice(0, 7),
);
function resetFileInput(event: Event) {
  (event.target as HTMLInputElement).value = "";
}
</script>

<template>
  <section class="panel">
    <div class="image-persona-picker">
      <span class="persona-label">您的身份是：</span
      ><el-select
        :model-value="persona"
        clearable
        placeholder="请选择身份"
        @update:model-value="emit('update:persona', $event)"
        ><el-option label="平面设计师" value="graphic_designer" /><el-option
          label="插画师"
          value="illustrator" /><el-option
          label="摄影师"
          value="photographer" /><el-option
          label="电商工作者"
          value="ecommerce_worker" /><el-option
          label="UI 设计师"
          value="ui_designer"
      /></el-select>
    </div>
    <div class="image-upload-area">
      <label class="upload-box"
        ><input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          :disabled="loading"
          @click="resetFileInput"
          @change="emit('select', $event)"
        /><img
          v-if="previewUrl"
          :src="previewUrl"
          class="image-preview"
          @click.prevent.stop="previewOpen = true"
        /><el-icon v-else size="34"><Picture /></el-icon
        ><strong>{{ imageName || "选择一张图片" }}</strong
        ><span>支持 JPG、PNG、WebP（最大 10MB）</span></label
      ><el-button
        v-if="imageName"
        class="clear-image-button"
        type="danger"
        plain
        @click="emit('delete')"
        >清空</el-button
      >
    </div>
    <el-button
      v-if="imageId"
      type="primary"
      class="primary-action"
      :loading="analyzing"
      @click="emit('analyze')"
      >识别关键词</el-button
    >
    <p v-if="error" class="error-text">{{ error }}</p>
    <el-dialog v-model="previewOpen" title="图片预览" width="min(90vw, 900px)"
      ><img :src="previewUrl" class="image-full-preview"
    /></el-dialog>
    <KeywordSelectionPanel
      v-if="suggestions.length"
      :suggestions="suggestions"
      :platforms="displayedPlatforms"
      :selected-platform="selectedPlatform"
      :final-query="finalQuery"
      @remove="(keyword) => emit('remove', keyword)"
      @select-platform="(platform) => emit('selectPlatform', platform)"
      @search="emit('search')"
      @update:final-query="(value) => emit('update:finalQuery', value)"
    />
  </section>
</template>
