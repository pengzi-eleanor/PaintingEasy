<script setup lang="ts">
defineProps<{ modelValue: string }>();
defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <section class="panel settings">
    <label class="section-label">默认素材平台</label
    ><el-select
      :model-value="modelValue"
      @update:model-value="$emit('update:modelValue', $event)"
      ><el-option label="Unsplash" value="unsplash" /><el-option
        label="Pexels"
        value="pexels" /><el-option
        label="Pixabay"
        value="pixabay" /></el-select
    ><el-alert
      title="当前版本仅使用本地 Mock 数据，不会上传图片或查询内容。"
      type="info"
      :closable="false"
      show-icon
    />
    <p class="version">CreatingEasy v0.1.0</p>
  </section>
</template>
