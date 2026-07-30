# 美股看板 — Vercel 部署

## 项目结构

```
vercel-app/
├── api/
│   ├── stock/[ticker].py     ← 报价+日线+资金流+公司信息
│   ├── news/[ticker].py      ← 新闻（Yahoo Search API）
│   └── compare/[ticker].py   ← 多空/机构数据（yfinance）
├── index.html                ← 前端页面
├── vercel.json               ← builds 声明（无需 rewrites）
└── requirements.txt          ← Python 依赖
```

## 部署方式

### GitHub 导入（推荐）

1. 登录 https://vercel.com → **Add New Project**
2. Import `xiki45/stock-dashboard`
3. Vercel 自动识别 `api/**/[ticker].py` 为 Python Serverless Functions
4. 点击 **Deploy**，几分钟后获得 `.vercel.app` 域名

### Vercel CLI

```bash
npm i -g vercel
cd vercel-app
vercel login
vercel --prod
```

## 数据源说明

| 模块 | API 端点 | 是否需要 yfinance |
|---|---|---|
| 报价 / 日线 / 资金流 | Yahoo Finance v8 Chart API | ❌ 纯 urllib |
| 新闻 | Yahoo Finance v1 Search API | ❌ 纯 urllib |
| 多空 / 机构持股 | yfinance → Yahoo Quote API | ✅ 需要 |

## 注意事项

1. **yfinance 包体积**：yfinance + pandas + curl_cffi ≈ 150MB，在 Vercel 免费版 250MB 限制内，但部署会比较慢
2. **超时风险**：Vercel 免费版 Serverless Function 超时 10s，yfinance 子进程调用约 5-8s，可能紧张。Pro 版 60s 无压力
3. **降级方案**：如果 yfinance 部署失败，删除 `requirements.txt` 中的 yfinance，代码会自动降级——报价/新闻/资金流正常，多空数据返回空值
4. **冷启动**：首次请求会有 2-3s 冷启动延迟，后续请求正常
