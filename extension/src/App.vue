<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  ArrowLeft,
  InfoFilled,
  Picture,
  Search,
  Setting,
  Timer,
} from "@element-plus/icons-vue";
import { ApiError } from "./api/http";
import { assistSearch, analyzeImage, uploadImage, track } from "./api/search";
import HistoryPanel from "./components/HistoryPanel.vue";
import ImageAnalyzePanel from "./components/ImageAnalyzePanel.vue";
import KeywordOptimizePanel from "./components/KeywordOptimizePanel.vue";
import PlatformGuidePanel from "./components/PlatformGuidePanel.vue";
import SettingsPanel from "./components/SettingsPanel.vue";
import {
  buildPlatformUrl,
  getRecommendedPlatformLinks,
} from "./config/imageSearchSites";
import type {
  OptimizationMode,
  SearchPlatformLink,
  SearchSuggestion,
} from "./types/search";
import { useHistoryStore } from "./stores/history";
import { useSearchStore } from "./stores/search";

const activeTab = ref("text"),
  query = ref("");
const currentView = ref<"main" | "settings">("main");
const imageName = ref(""),
  imageSuggestions = ref<SearchSuggestion[]>([]),
  imageFinalQuery = ref(""),
  imageSelectedPlatform = ref("unsplash"),
  defaultPlatform = ref("unsplash"),
  imageId = ref(""),
  imagePreview = ref(""),
  imageLoading = ref(false),
  imageAnalyzing = ref(false),
  imageError = ref("");
const savedPersona =
  globalThis.localStorage?.getItem("painting-easy-default-persona") || "";
const textPersona = ref(savedPersona);
const imagePersona = ref(savedPersona);
const defaultPersona = ref(savedPersona);
watch([textPersona, imagePersona], ([text, image]) => {
  const firstChoice = text || image;
  if (!defaultPersona.value && firstChoice) {
    defaultPersona.value = firstChoice;
    globalThis.localStorage?.setItem(
      "painting-easy-default-persona",
      firstChoice,
    );
  }
});
const history = useHistoryStore();
const search = useSearchStore();
const imagePlatforms = computed<SearchPlatformLink[]>(() =>
  getRecommendedPlatformLinks(imagePersona.value || undefined),
);
watch(
  imagePlatforms,
  (platforms) => {
    if (
      !platforms.some((item) => item.platform === imageSelectedPlatform.value)
    ) {
      imageSelectedPlatform.value = platforms[0]?.platform ?? "";
    }
  },
  { immediate: true },
);
const selectedKeywords = computed(() =>
  search.suggestions
    .filter((item) => item.selected)
    .map((item) => item.keyword),
);
function searchSelected() {
  if (!search.selectedPlatform || !selectedKeywords.value.length) return;
  const platform = search.platforms.find(
    (item) => item.platform === search.selectedPlatform,
  );
  const url = platform?.supports_search_url
    ? buildPlatformUrl(
        search.selectedPlatform,
        selectedKeywords.value.join(" "),
      )
    : platform?.url;
  if (url) window.open(url, "_blank");
}

async function optimize() {
  if (!query.value.trim() || !textPersona.value || !search.optimizationMode)
    return;
  search.start(query.value);
  const startedAt = performance.now();
  await track("search_session_start", { entry: "text" });
  try {
    const result = await assistSearch(
      query.value,
      "auto",
      textPersona.value,
      undefined,
      search.optimizationMode as OptimizationMode,
      false,
    );
    search.succeed(result);
    await track("keyword_suggestions_generated", {
      entry: "text",
      suggestion_count: result.suggestions.length,
      provider: result.provider,
      degraded: result.degraded,
    });
    await track("platform_links_generated", {
      count: result.platforms.length,
      degraded: result.degraded,
      elapsed_ms: performance.now() - startedAt,
    });
    if (selectedKeywords.value.length)
      history.add(result.original_query, selectedKeywords.value);
  } catch (error) {
    search.fail(
      error instanceof ApiError ? error.message : "搜索服务暂时不可用",
    );
  }
}
async function handleImage(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  imageName.value = file.name;
  imagePreview.value = URL.createObjectURL(file);
  imageError.value = "";
  imageLoading.value = true;
  try {
    const result = await uploadImage(file);
    imageId.value = result.image_id;
  } catch (error) {
    imageError.value =
      error instanceof ApiError ? error.message : "图片上传失败";
  } finally {
    imageLoading.value = false;
  }
}
async function analyzeUploadedImage() {
  if (!imageId.value || imageAnalyzing.value) return;
  imageAnalyzing.value = true;
  imageError.value = "";
  try {
    const result = await analyzeImage(
      imageId.value,
      imagePersona.value || undefined,
      imageSelectedPlatform.value,
    );
    imageSuggestions.value = result.suggestions;
    imageFinalQuery.value = result.suggestions
      .map((item) => item.keyword)
      .join(" ");
  } catch (error) {
    imageError.value =
      error instanceof ApiError ? error.message : "图片识别失败";
  } finally {
    imageAnalyzing.value = false;
  }
}
function searchImageSelected() {
  const selected = imageSuggestions.value
    .filter((item) => item.selected)
    .map((item) => item.keyword)
    .join(" ");
  const platform = imagePlatforms.value.find(
    (item) => item.platform === imageSelectedPlatform.value,
  );
  const url = platform?.supports_search_url
    ? buildPlatformUrl(imageSelectedPlatform.value, selected)
    : platform?.url;
  if (url) window.open(url, "_blank");
}
function removeImageSuggestion(id: string) {
  imageSuggestions.value = imageSuggestions.value.filter(
    (item) => item.id !== id,
  );
  imageFinalQuery.value = imageSuggestions.value
    .map((item) => item.keyword)
    .join(" ");
}
function deleteImage() {
  if (imagePreview.value) URL.revokeObjectURL(imagePreview.value);
  imageName.value = "";
  imageId.value = "";
  imagePreview.value = "";
  imageSuggestions.value = [];
  imageFinalQuery.value = "";
  imageError.value = "";
}
function setDefaultPersona(value: string) {
  defaultPersona.value = value;
  globalThis.localStorage?.setItem("painting-easy-default-persona", value);
}
</script>
<template>
  <main class="popup-shell">
    <header class="brand">
      <div class="brand-mark">C</div>
      <div>
        <h1>CreatingEasy</h1>
        <p>让素材搜索更简单</p>
      </div>
      <button
        class="brand-guide-button"
        type="button"
        @click="currentView = currentView === 'settings' ? 'main' : 'settings'"
      >
        <el-icon
          ><ArrowLeft v-if="currentView === 'settings'" /><Setting
            v-else /></el-icon
        ><span>{{ currentView === "settings" ? "返回" : "设置" }}</span>
      </button>
    </header>
    <SettingsPanel
      v-if="currentView === 'settings'"
      v-model="defaultPlatform"
      :persona-value="defaultPersona"
      @update:persona-value="setDefaultPersona"
    />
    <el-tabs v-else v-model="activeTab" stretch class="main-tabs">
      <el-tab-pane name="text"
        ><template #label
          ><el-icon><Search /></el-icon><span>文本</span></template
        ><KeywordOptimizePanel
          :suggestions="search.suggestions"
          :platforms="search.platforms"
          :selected-platform="search.selectedPlatform"
          :error="search.error"
          :warning="search.warning"
          :final-query="search.finalQuery"
          @retry="optimize"
          @remove="search.removeSuggestion"
          @select-platform="search.selectedPlatform = $event"
          @search="searchSelected"
          @update:final-query="search.finalQuery = $event"
          ><template #input
            ><div class="search-heading">
              <div>
                <strong>输入素材关键词</strong
                ><small>描述主体、场景或风格</small>
              </div>
              <span>Ctrl + Enter</span>
            </div>
            <el-input
              v-model="query"
              type="textarea"
              :rows="3"
              maxlength="200"
              show-word-limit
              placeholder="例如：暖色调咖啡店宣传海报"
              @keyup.ctrl.enter="optimize"
            />
            <div class="search-options">
              <div class="persona-picker">
                <span class="persona-label">您的身份是：</span
                ><el-select
                  v-model="textPersona"
                  clearable
                  placeholder="请选择"
                  class="persona-select"
                  ><el-option
                    label="平面设计师"
                    value="graphic_designer" /><el-option
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
              <div class="optimization-picker">
                <span class="persona-label">搜索方式：</span>
                <el-radio-group v-model="search.optimizationMode">
                  <el-radio-button value="basic">基础优化</el-radio-button>
                  <el-radio-button value="smart">智能优化</el-radio-button>
                </el-radio-group>
              </div>
            </div>
            <small class="mode-hint" v-if="search.optimizationMode === 'basic'"
              >使用规则与知识来源，不消耗 AI 次数</small
            >
            <small
              class="mode-hint"
              v-else-if="search.optimizationMode === 'smart'"
              >智能优化会消耗 AI 额度<span
                v-if="search.generationStatus?.remaining_uses != null"
                >；剩余 {{ search.generationStatus.remaining_uses }} 次</span
              ><span v-if="search.generationStatus?.status === 'fallback'"
                >；本次已降级为基础优化</span
              ></small
            >
            <el-button
              type="primary"
              class="primary-action"
              :loading="search.loading"
              :disabled="
                !query.trim() || !textPersona || !search.optimizationMode
              "
              @click="optimize"
              >{{
                search.optimizationMode === "smart"
                  ? "智能优化关键词"
                  : "基础优化关键词"
              }}</el-button
            ></template
          ></KeywordOptimizePanel
        ></el-tab-pane
      >
      <el-tab-pane name="image"
        ><template #label
          ><el-icon><Picture /></el-icon><span>识图</span></template
        ><ImageAnalyzePanel
          :image-name="imageName"
          :suggestions="imageSuggestions"
          :platforms="imagePlatforms"
          :selected-platform="imageSelectedPlatform"
          :final-query="imageFinalQuery"
          :persona="imagePersona"
          :preview-url="imagePreview"
          :image-id="imageId"
          :loading="imageLoading"
          :analyzing="imageAnalyzing"
          :error="imageError"
          @select="handleImage"
          @update:persona="imagePersona = $event"
          @analyze="analyzeUploadedImage"
          @delete="deleteImage"
          @remove="removeImageSuggestion"
          @update:final-query="imageFinalQuery = $event"
          @select-platform="imageSelectedPlatform = $event"
          @search="searchImageSelected"
      /></el-tab-pane>
      <el-tab-pane name="history"
        ><template #label
          ><el-icon><Timer /></el-icon><span>历史</span></template
        ><HistoryPanel :items="history.items" @clear="history.clear"
      /></el-tab-pane>
      <el-tab-pane name="guide"
        ><template #label
          ><el-icon><InfoFilled /></el-icon><span>平台介绍</span></template
        ><PlatformGuidePanel
      /></el-tab-pane>
    </el-tabs>
    <footer class="data-credit">感谢数据支持：腾讯 AI Lab 中文词向量</footer>
  </main>
</template>
