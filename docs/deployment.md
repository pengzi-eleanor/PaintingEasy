# 部署与公网知识扩展

腾讯轻量中文词向量默认在后端本地运行，模型文件放在 `backend/data/models/light_Tencent_AILab_ChineseEmbedding.bin`，可通过 `TENCENT_WORD2VEC_ENABLED=false` 关闭。ConceptNet 默认关闭；Wikidata 仍是可选网络扩展，不需要 API key，部署方应设置可识别的 `KNOWLEDGE_USER_AGENT`。用户可以在插件设置中关闭 Wikidata，但这不会关闭本地腾讯词向量。

按 README 从 `backend` 目录启动时，默认缓存位于 `data/knowledge_cache.sqlite3`；生产部署应为该目录提供持久、可写存储。缓存不可用时搜索仍会继续实时请求或回退原始 query。

基础优化启用网络扩展时，只发送当前搜索词、语言及必要的请求限制；不发送图片、历史、AI Prompt、密钥或原始外部响应。SQLite 只保存 query 摘要、标准化候选及必要状态。日志仅记录 Provider、异常类型和重试序号，不记录完整 query、请求 URL 参数或响应正文。

## 2026-09-10 目标环境冒烟结果

使用固定的非敏感测试词，每个官方地址执行 5 次最小请求：

| Provider | 官方地址 | 状态码 | P95 | 超时 | HTTP 429 | Retry-After |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Wikidata | `https://www.wikidata.org/w/api.php` | 403 × 5 | 490.9 ms | 0 | 0 | 0 |
| ConceptNet | `https://api.conceptnet.io` | 502 × 5 | 1390.2 ms | 0 | 0 | 0 |

因此，本次目标部署网络未通过真实连通性验收。完整搜索 API 对真实请求返回两个 `original_fallback`，保留规范化原始 query 和平台跳转，没有绕过网络限制，也没有使用 Mock 冒充在线成功。

独立冒烟工具随后用明确标记的脱敏 fixture 验证完整 API 状态机：双 `live`、双 `fresh_cache`、`live + original_fallback` 部分成功、`stale_cache` 旧缓存回退，以及双 `original_fallback`。这些状态仅证明缓存和降级装配有效，不代表当前部署网络已连接成功。

真实冒烟需人工显式运行，不属于 pytest：

```powershell
cd backend
python scripts/smoke_external_knowledge.py
```

上线前应在实际部署网络再次运行；若仍为 403/502，应继续依赖合格旧缓存或原始 query 回退，不应配置代理绕过当地网络或服务限制。
