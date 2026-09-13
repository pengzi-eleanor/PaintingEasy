<script setup lang="ts">
import { searchablePlatformOptions } from "../config/imageSearchSites";
defineProps<{ modelValue: string; personaValue?: string }>();
defineEmits<{
  "update:modelValue": [value: string];
  "update:personaValue": [value: string];
}>();
</script>

<template>
  <section class="panel settings">
    <label class="section-label">默认身份</label
    ><el-select
      :model-value="personaValue"
      clearable
      placeholder="首次选择后自动记住"
      @update:model-value="$emit('update:personaValue', $event)"
      ><el-option label="平面设计师" value="graphic_designer" /><el-option
        label="插画师" value="illustrator" /><el-option
        label="摄影师" value="photographer" /><el-option
        label="电商工作者" value="ecommerce_worker" /><el-option
        label="UI 设计师" value="ui_designer"
    /></el-select>
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
