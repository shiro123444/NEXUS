<p align="center">
  <img src="assets/icon.svg" width="80" height="96" alt="Kiro Kroxy">
</p>

<h1 align="center">Kiro Kroxy</h1>

<p align="center">
  公益 AI API 服务平台 — 模型广场、计费网关、多协议代理一站式方案
</p>

<p align="center">
  <a href="#项目简介">简介</a> •
  <a href="#架构概览">架构</a> •
  <a href="#功能特性">功能</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#项目结构">项目结构</a> •
  <a href="#许可证">许可证</a>
</p>

<p align="center">
  <strong>中文</strong> | <a href="README_EN.md">English</a>
</p>

---

## 项目简介

Kiro Kroxy 是一套完整的公益 AI API 服务平台框架，为社区用户提供稳定、经济的 AI 模型访问服务。

**线上地址：**
- 用户门户：[portal.wbuai.me](https://portal.wbuai.me)
- API 端点：[api.wbuai.me](https://api.wbuai.me)（Anthropic 协议）
- OpenAI 兼容端点：[openai.wbuai.me](https://openai.wbuai.me)

### 平台组件

| 组件 | 技术栈 | 说明 |
|------|--------|------|
| **kiro.rs** | Rust (axum + reqwest) | 高性能 Anthropic API 反向代理引擎，处理模型路由与协议转换 |
| **Portal 后端** | Python (FastAPI) | 用户系统、模型广场、账号管理、数据持久化 |
| **Portal 前端** | React + Vite + Tailwind | 用户仪表盘、模型广场、用量统计 |
| **计费网关** | Python (FastAPI) | 独立计费服务，按模型定价、促销折扣、用量扣费 |
| **Nginx** | Nginx | 反向代理路由，SSL 终端 |

---

## 架构概览

```
用户浏览器                   AI 客户端 (Claude Code / Codex / 自定义)
    │                              │
    ▼                              ▼
portal.wbuai.me              api.wbuai.me / openai.wbuai.me
 (Nginx :443)                    (Nginx :443)
    │                              │
    ▼                              ▼
Portal 后端 (:8080)          计费网关 (:8300)
    │                              │
    │                              ▼
    │                          kiro.rs (:8990)
    │                              │
    │                              ▼
    │                         Anthropic API
    │
    ▼
 SQLite (portal.db)
```

- **Portal** 处理用户注册、登录、模型广场浏览、API Key 管理
- **计费网关** 在 API 请求路径中拦截，验证 API Key、按模型定价扣费、应用促销折扣
- **kiro.rs** 负责将请求转换为 Anthropic 原生协议并转发，处理流式响应

---

## 功能特性

### 用户侧
- **模型广场** — 浏览全部可用模型，查看定价、上下文窗口、能力描述，按系列筛选
- **API Key 管理** — 自助创建和管理 API Key，直接对接 Anthropic Messages API
- **用量统计** — 实时查看 Token 用量、费用明细
- **促销公告** — 首页弹窗 + 横幅展示限时优惠活动

### 管理侧
- **用户管理** — 用户列表、余额调整、状态管理
- **Key 管理** — 批量创建/轮换/撤销 API Key
- **定价管理** — 模型上下架、价格调整、促销活动配置
- **用量监控** — 全局用量趋势、按用户/模型统计

### 代理引擎 (kiro.rs)
- **多协议支持** — Anthropic Messages API、OpenAI Chat Completions、OpenAI Responses
- **流式响应** — 完整 SSE 流式支持，含工具调用流式增量
- **模型映射** — 智能模型名称映射，支持别名、连字符、日期后缀
- **工具调用** — Anthropic / OpenAI 双协议工具调用完整支持
- **图片理解** — 支持图片输入转发

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 22+ (前端构建)
- Rust 1.92+ (kiro.rs 编译)
- Docker (容器化部署)
- Nginx (反向代理)

### 本地开发

```bash
# 克隆项目
git clone git@github.com:shiro123444/Kiro-Kroxy.git
cd Kiro-Kroxy

# 后端
cd kiro_proxy
pip install -r requirements.txt
uvicorn portal.user_app:app --host 0.0.0.0 --port 8080

# 前端
cd portal-web
pnpm install
pnpm dev

# 计费网关
cd /opt/billing-gateway
uvicorn gateway:app --host 0.0.0.0 --port 8300

# kiro.rs (Docker 构建)
cd kiro.rs
docker build -t kiro-rs:local .
docker run -d -p 8990:8990 -v $(pwd)/config:/app/config kiro-rs:local
```

### Docker 部署

项目核心组件均支持 Docker 化部署：

- **kiro.rs**: `kiro.rs/Dockerfile` — 多阶段构建（Node 前端 + Rust 编译 + Alpine 运行时）
- **Portal**: 通过 systemd 管理或 Docker Compose
- **计费网关**: 独立 FastAPI 服务

---

## 项目结构

```
Kiro-Kroxy/
├── kiro.rs/                    # Rust 代理引擎
│   ├── src/
│   │   ├── main.rs            # 入口
│   │   ├── anthropic/         # Anthropic 协议处理 (handlers, converter)
│   │   ├── openai/            # OpenAI 协议兼容
│   │   ├── http_client.rs     # HTTP 客户端 (连接池复用)
│   │   └── token.rs           # Token 管理
│   ├── admin-ui/              # 内嵌管理界面 (React)
│   └── Dockerfile             # 多阶段构建
│
├── kiro_proxy/                 # Python Portal 后端
│   ├── portal/
│   │   ├── user_app.py        # 用户端 FastAPI 应用
│   │   ├── admin_portal.py    # 管理端 API
│   │   ├── auth.py            # 用户认证
│   │   └── db.py              # 数据库模型
│   ├── handlers/              # 协议处理器
│   │   ├── anthropic.py       # /v1/messages
│   │   ├── openai.py          # /v1/chat/completions
│   │   └── responses.py       # /v1/responses (Codex CLI)
│   └── core/                  # 核心模块 (账号、状态、统计)
│
├── portal-web/                 # React 前端
│   └── src/pages/
│       ├── Client.jsx          # 用户仪表盘 (模型广场、Key管理、用量)
│       └── Admin.jsx           # 管理面板
│
├── opt/billing-gateway/        # 计费网关 (独立部署)
│   └── gateway.py              # FastAPI 计费服务
│
├── scripts/                    # 运维脚本
├── docs/                       # 文档
└── assets/                     # 资源文件
```

---

## API 端点

### 公开 API（经过计费网关）

| 协议 | 端点 | 说明 |
|------|------|------|
| Anthropic | `POST /v1/messages` | Messages API（Claude Code / 自定义客户端） |
| Anthropic | `POST /v1/messages/count_tokens` | Token 计数 |
| OpenAI | `POST /v1/chat/completions` | Chat Completions API |
| OpenAI | `POST /v1/responses` | Responses API (Codex CLI) |
| OpenAI | `GET /v1/models` | 模型列表 |

> 认证方式：在 HTTP Header 中携带 `x-api-key: sk-kiro-rs-xxxx`，费用按模型定价从账户余额扣除。

### Portal API（用户门户内部）

| 端点 | 说明 |
|------|------|
| `GET /api/models` | 模型广场数据（含定价、促销） |
| `POST /api/auth/login` | 用户登录 |
| `POST /api/auth/register` | 用户注册 |
| `GET /api/keys` | API Key 管理 |
| `GET /api/usage` | 用量统计 |

---

## 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 了解版本更新历史。

## 贡献

欢迎贡献代码！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与。

## 免责声明

本项目仅供学习研究，禁止商用。使用本项目产生的任何后果由使用者自行承担，与作者无关。

本项目与 Kiro / AWS / Anthropic 官方无关。

## 许可证

MIT License
