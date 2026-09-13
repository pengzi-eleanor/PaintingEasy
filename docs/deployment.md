# 后端部署与 Provider 边界

腾讯轻量中文词向量在后端本地运行，模型文件放在
`backend/data/models/light_Tencent_AILab_ChineseEmbedding.bin`。查询不会发送到腾讯服务。

相关配置：

- `TENCENT_WORD2VEC_ENABLED`：是否启用本地词向量；
- `TENCENT_WORD2VEC_MODEL_PATH`：模型文件路径；
- `TENCENT_WORD2VEC_TOPN`、`TENCENT_WORD2VEC_MIN_SIMILARITY`：候选限制；
- `SEARCH_CACHE_MAX_ENTRIES`、`SEARCH_CACHE_TTL_SECONDS`：当前进程内的轻量结果缓存；
- `EXTERNAL_API_TIMEOUT_SECONDS`、`EXTERNAL_API_RETRY_COUNT`：未来外部 API 的公共默认值。
- `IMAGE_UPLOAD_MAX_SIZE_MB`：上传图片大小上限，默认 10MB；
- `IMAGE_EXPIRE_HOURS`：上传图片保留时长，默认 24 小时；
- `IMAGE_CLEANUP_INTERVAL_MINUTES`：服务运行时扫描并清理过期图片的间隔，默认 60 分钟。服务启动时也会立即清理一次，因此上次关停后遗留的过期文件不会永久保留。

缓存仅保存在当前后端进程内，缓存键使用查询摘要；服务重启后自动清空，不承担永久知识库职责。

项目不再包含 Wikidata 或 ConceptNet。未来翻译、大模型和图片语义识别服务应分别实现
`TranslationProvider`、`LanguageModelProvider`、`ImageAnalyzeProvider`，通过依赖注入装配。
通用 `HttpxExternalApiClient` 提供超时、有限重试、JSON 解析和脱敏错误映射；API 密钥只能从环境变量读取。
