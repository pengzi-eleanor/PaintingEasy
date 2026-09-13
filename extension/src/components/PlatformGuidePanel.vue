<script setup lang="ts">
import catalog from "../../../shared/platforms.json";
import { getCopyrightLabel } from "../config/imageSearchSites";
</script>

<template>
  <section class="panel platform-guide">
    <div class="guide-heading">
      <div><strong>素材平台介绍</strong><small>平台顺序和启用状态均可按需审核调整</small></div>
      <span>{{ catalog.config_version }}</span>
    </div>
    <div class="platform-guide-list">
      <a
        v-for="platform in catalog.platforms"
        :key="platform.id"
        class="platform-guide-item"
        :href="platform.homepage_url"
        target="_blank"
        rel="noopener noreferrer"
      >
        <div class="platform-guide-title">
          <strong>{{ platform.name }}</strong>
          <em>{{ getCopyrightLabel(platform.copyright_status) }}</em>
        </div>
        <p>{{ platform.recommendation_reason }}</p>
        <div class="platform-guide-meta">
          <span>擅长：{{ platform.strengths.join("、") }}</span>
          <em v-if="platform.requires_login">需登录</em>
          <em v-if="!platform.enabled">已停用</em>
        </div>
      </a>
    </div>
  </section>
</template>
