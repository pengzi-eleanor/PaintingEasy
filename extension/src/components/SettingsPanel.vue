<script setup lang="ts">
import { searchablePlatformOptions } from "../config/imageSearchSites";
defineProps<{ modelValue: string; networkExpansion: boolean }>();
defineEmits<{
  "update:modelValue": [value: string];
  "update:networkExpansion": [value: boolean];
}>();
</script>

<template>
  <section class="panel settings">
    <label class="section-label">默认素材平台</label
    ><el-select
      :model-value="modelValue"
      @update:model-value="$emit('update:modelValue', $event)"
      ><el-option
        v-for="platform in searchablePlatformOptions"
        :key="platform.value"
        :label="platform.label"
        :value="platform.value"
      /></el-select
    ><label class="section-label">公共知识扩展</label
    ><el-switch
      :model-value="networkExpansion"
      active-text="启用 Wikidata"
      inactive-text="关闭网络扩展"
      @update:model-value="$emit('update:networkExpansion', $event)"
    />
    ><el-alert
      title="腾讯词向量始终在本地运行；启用后，仅会把本次搜索词发送到 Wikidata。"
      type="info"
      :closable="false"
      show-icon
    />
    <p class="version">CreatingEasy v0.1.0</p>
  </section>
</template>
