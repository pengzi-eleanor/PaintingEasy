<script setup lang="ts">
import { searchablePlatformOptions } from "../config/imageSearchSites";
defineProps<{ modelValue: string }>();
defineEmits<{
  "update:modelValue": [value: string];
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
    ><el-alert
      title="腾讯中文词向量在本地运行，搜索词不会发送到公共知识服务。"
      type="info"
      :closable="false"
      show-icon
    />
    <p class="version">CreatingEasy v0.1.0</p>
  </section>
</template>
