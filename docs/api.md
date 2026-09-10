# CreatingEasy API

默认地址：`http://127.0.0.1:8000`。响应均为 JSON（图片上传接口的请求为 `multipart/form-data`）。当前业务接口返回确定性的 mock 数据。

打开根地址 `/` 只返回服务说明，不会执行关键词搜索。关键词接口必须使用 `POST /api/v1/search/assist` 并发送 JSON 请求体。

> **离线 RAG-ready：** 当前使用本地小型知识库、规则/别名检索和确定性的 Mock Embedding/LLM provider，不调用真实图库、Embedding 或 LLM API，也不下载模型。

## POST /api/v1/search/assist

响应同时返回新领域字段 `core_terms`、`expanded_terms`、`platform_terms`、`default_query`、`platform_queries`、`retrieval` 和 `warnings`。`retrieval.strategy` 为 `rules_only`、`hybrid` 或 `fallback`；`degraded` 仅表示检索降级，不表示请求失败。当前离线 Mock Embedding 使用 `hybrid` 标识，Embedding 未启用时必须为 `rules_only`，失败且无候选时为 `fallback`。旧的 `query`、`suggestions`、`platforms` 是由上述新模型派生的兼容视图，后续可在 `/api/v2/search/assist` 独立迁移。

示例：

```json
{"original_query":"暖色咖啡店","core_terms":[],"expanded_terms":[],"platform_terms":[],"default_query":"coffee warm lighting","platform_queries":[],"retrieval":{"strategy":"hybrid","embedding_enabled":true,"embedding_provider":"mock","embedding_model":"deterministic-mock","knowledge_base_version":"keyword-knowledge-v1","candidate_count":2,"degraded":false},"warnings":[],"query":"coffee warm lighting","suggestions":[],"platforms":[]}
```

统一搜索入口。请求体为 `{"query":"暖色调咖啡店宣传海报","language":"auto","persona":"graphic_designer","platforms":["unsplash","pexels"]}`。`query` 去除首尾空白后长度为 1–500；`language` 为 `auto`、`zh` 或 `en`；`persona` 和 `platforms` 可选。

前端当前提供 `graphic_designer`、`illustrator`、`photographer`、`ecommerce_worker` 和 `ui_designer` 五种角色值。未选择时不发送 `persona`，后端保持原有行为。

响应包含 `original_query`、平台 query、`suggestions`、`platforms`，以及来源和降级字段。每个 suggestion 是稳定 ID 的 `KeywordCandidate`：包含 `concept_id`、展示词、语言、分类、`core`/`expanded`/`platform_specific` 分组、来源、可删除标记、`derived_from` 和适用平台。`scores` 内的五项分数及 `final_score` 均为 0–1；最终分数按 `exact_match*0.35 + semantic_similarity*0.20 + relation_weight*0.15 + persona_weight*0.15 + platform_weight*0.15` 确定性计算并校验。非原始词必须有原因和来源候选。旧的单一 `confidence` 不再作为对外评分字段；原始 query 始终保留为安全回退。

调用流程为：原始 query → 现有规则提取 → 关键词/角色/平台规则离线检索 → Context Builder → Mock LLM → Pydantic 校验 → 去重合并 → 平台 query。角色规则用于调整主体、场景、颜色、风格和构图建议；平台规则用于平台偏好，不得改变原始意图。Embedding 失败回退规则逻辑；LLM 失败或非法结构回退规则和检索结果；无匹配时保留原始 query；空输入不调用 provider。

未来接入真实服务时，只需替换 `backend/app/providers.py` 中 `EmbeddingProvider` 和 `LanguageModelProvider` 的实现，并通过依赖注入传给 service；路由、service 和前端主要契约无需改写。

## GET /health

成功响应 `200`：

```json
{"status": "ok", "service": "creating-easy-backend"}
```

## POST /api/text/optimize

请求：

```json
{"query": "暖色调咖啡店宣传海报", "language": "auto"}
```

- `query`：必填，去除首尾空白后长度为 1–500。
- `language`：可选，`auto`、`zh` 或 `en`，默认为 `auto`。

成功响应 `200`：

```json
{
  "original_query": "暖色调咖啡店宣传海报",
  "suggestions": [
    {"keyword": "暖色调咖啡店宣传海报", "category": "general", "selected": true},
    {"keyword": "creative asset", "category": "style", "selected": true}
  ],
  "provider": "mock",
  "is_ai_generated": true
}
```

无效输入返回 `422`。接口始终保留原始意图，建议词由用户自行取舍。

## POST /api/image/analyze

使用 `multipart/form-data` 上传字段 `image`。允许 JPEG、PNG、WebP，最大 10 MB；服务会检查媒体类型、文件签名和大小，mock 阶段不会调用外部模型。

成功响应 `200`：

```json
{
  "filename": "reference.png",
  "keywords": [
    {"keyword": "minimal workspace", "category": "scene", "confidence": 0.94}
  ],
  "provider": "mock",
  "is_ai_generated": true
}
```

- 不支持的类型返回 `415`。
- 超过大小限制返回 `413`。
- 声明类型与文件内容不符返回 `422`。
- 缺少文件返回 `422`。

接入真实模型时响应结构保持稳定，供应商字段不得泄漏到此契约。
