# CreatingEasy

CreatingEasy 是面向创作者的素材搜索辅助 Chrome 插件 monorepo。当前版本提供可独立运行的 Vue 3 插件界面和 FastAPI mock 服务，为后续图库适配、AI 关键词生成与图片语义识别保留稳定边界。

## 目录

```text
extension/  Chrome Extension（Vue 3 + TypeScript + Vite）
backend/    FastAPI 服务与 Pydantic API 模型
docs/       产品、接口与路线图文档
```

## 环境要求

- Node.js 20+、npm 10+
- Python 3.11+
- Chrome 或 Chromium 浏览器

## 运行插件前端

```bash
cd extension
npm install
npm run dev
```

开发页面默认打开 `http://localhost:5173`。生成可加载的 Chrome 插件：

```bash
npm run build
```

然后打开 Chrome 的 `chrome://extensions`，开启“开发者模式”，选择“加载已解压的扩展程序”，选中 `extension/dist`。

## 运行后端

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

服务默认位于 `http://127.0.0.1:8000`，健康检查为 `GET /health`，统一搜索辅助接口为 `POST /api/v1/search/assist`，交互式接口文档位于 `/docs`。该接口当前仅使用规则 Mock，不调用真实图库或 AI 服务。

## 验证

```bash
cd extension
npm run type-check
npm run test
npm run build

cd ../backend
pytest
ruff check .
```

更多信息见 [产品说明](docs/product.md)、[API 说明](docs/api.md) 和 [开发路线图](docs/roadmap.md)。
