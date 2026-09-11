# CreatingEasy API

默认地址：`http://127.0.0.1:8000`。响应均为 JSON（图片上传接口的请求为 `multipart/form-data`）。当前业务接口返回确定性的 mock 数据。

打开根地址 `/` 只返回服务说明，不会执行关键词搜索。关键词接口必须使用 `POST /api/v1/search/assist` 并发送 JSON 请求体。

> **离线智能优化：** `smart` 当前使用可替换的结构化 Mock LLM Provider，不调用真实付费模型或公网。原始 Provider 响应必须在 Provider 内解析为严格 Pydantic 模型后才能进入搜索服务。

> **关键词扩展：** 腾讯轻量中文词向量默认从后端本地文件读取，不发送 query。模型缺失或关闭时保留原始 query。`network_expansion` 暂时只作为旧客户端兼容字段，不再触发公共知识服务。

## POST /api/v1/search/assist

响应同时返回新领域字段 `core_terms`、`expanded_terms`、`platform_terms`、`default_query`、`platform_queries`、`retrieval` 和 `warnings`。`retrieval.strategy` 为 `rules_only`、`hybrid` 或 `fallback`；`degraded` 仅表示检索降级，不表示请求失败。当前离线 Mock Embedding 使用 `hybrid` 标识，Embedding 未启用时必须为 `rules_only`，失败且无候选时为 `fallback`。旧的 `query`、`suggestions`、`platforms` 是由上述新模型派生的兼容视图，后续可在 `/api/v2/search/assist` 独立迁移。

示例：

```json
{"original_query":"暖色咖啡店","core_terms":[],"expanded_terms":[],"platform_terms":[],"default_query":"coffee warm lighting","platform_queries":[],"retrieval":{"strategy":"hybrid","embedding_enabled":true,"embedding_provider":"mock","embedding_model":"deterministic-mock","knowledge_base_version":"keyword-knowledge-v1","candidate_count":2,"degraded":false},"warnings":[],"query":"coffee warm lighting","suggestions":[],"platforms":[]}
```

统一搜索入口。请求体为 `{"query":"暖色调咖啡店宣传海报","language":"auto","persona":"graphic_designer","optimization_mode":"basic","platforms":["unsplash","pexels"]}`。`query` 去除首尾空白后最长 500 字；`language` 为 `auto`、`zh` 或 `en`；`persona` 和 `platforms` 可选。`optimization_mode` 为 `basic` 或 `smart`，旧请求缺失时按 `basic` 处理。

响应保留 `query`、`suggestions`、`platforms` 等旧字段，并提供 `optimization_mode`、`knowledge_sources`、`platform_recommendations`、`core_intent_category`、`uncertainties` 和 `generation_status`。基础模式不会调用 LLM，生成状态为 `not_requested`；智能模式调用结构化 Provider，成功时为 `generated`，失败或额度不足时为 `fallback` 并返回完整基础结果。`generation_status.remaining_uses` 是前端可见的剩余次数；响应不会包含 API 密钥、Prompt 或原始模型响应。

前端当前提供 `graphic_designer`、`illustrator`、`photographer`、`ecommerce_worker` 和 `ui_designer` 五种角色值。未选择时不发送 `persona`，后端保持原有行为。

响应包含 `original_query`、平台 query、`suggestions`、`platforms`，以及来源和降级字段。每个 suggestion 是稳定 ID 的 `KeywordCandidate`：包含 `concept_id`、展示词、语言、分类、`core`/`expanded`/`platform_specific` 分组、来源、可删除标记、`derived_from` 和适用平台。`scores` 内的五项分数及 `final_score` 均为 0–1；最终分数按 `exact_match*0.35 + semantic_similarity*0.20 + relation_weight*0.15 + persona_weight*0.15 + platform_weight*0.15` 确定性计算并校验。非原始词必须有原因和来源候选。旧的单一 `confidence` 不再作为对外评分字段；原始 query 始终保留为安全回退。

调用流程为：基础候选 → 受控 Context Builder → 结构化 LLM Provider → 原义与平台白名单校验 → 去重合并 → 后端平台连接器生成 query/URL。Prompt 只包含原始描述、语言、职业上下文、标准化知识候选、允许的平台规则与固定数量限制。输出包含核心意图分类、最多 6 个核心词、最多 8 个扩展词、来源、原因、不确定项及最多 5 个有序平台方案；额外字段和 URL 均不被接受。非法 JSON、超量、未知平台、无依据新主体、超时或额度不足统一回退基础优化。

未来接入真实服务时，只需替换 `backend/app/providers.py` 中 `LanguageModelProvider` 的实现，并在 Provider 内完成外部 JSON 解析和严格模型校验，再通过依赖注入传给 service；平台 URL 始终由后端连接器生成。密钥只允许从 `AI_PROVIDER_API_KEY` 环境变量读取。`AI_PROVIDER` 默认 `mock`，`AI_SMART_QUOTA` 设置当前进程的可用次数；本阶段不会按非 mock 配置发起真实请求。

### Provider 与缓存配置

腾讯词向量是当前唯一关键词知识提供器。翻译、大模型和图片语义识别保留独立 Provider 接口，可使用通用 HTTP 客户端接入外部服务。当前轻量缓存为有界进程内 TTL 缓存，只保存摘要键和标准化结果，服务重启后清空。

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
