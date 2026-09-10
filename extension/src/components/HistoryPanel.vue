<script setup lang="ts">
import { Delete } from "@element-plus/icons-vue";
import type { SearchHistoryItem } from "../types/search";
defineProps<{ items: SearchHistoryItem[] }>();
defineEmits<{ clear: [] }>();
</script>

<template>
  <section class="panel">
    <div class="section-heading">
      <label class="section-label">最近搜索</label
      ><el-button
        v-if="items.length"
        text
        type="danger"
        :icon="Delete"
        @click="$emit('clear')"
        >清空</el-button
      >
    </div>
    <el-empty
      v-if="!items.length"
      description="还没有搜索记录"
      :image-size="72"
    />
    <article v-for="item in items" :key="item.id" class="history-item">
      <strong>{{ item.query }}</strong
      ><small>{{ item.createdAt }}</small>
      <p>{{ item.keywords.join(" · ") }}</p>
    </article>
  </section>
</template>
