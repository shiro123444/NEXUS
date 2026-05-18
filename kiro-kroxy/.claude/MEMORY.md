# Kiro-Kroxy 项目记忆

## 项目概述
Kiro API Proxy - 一个反向代理服务，支持多账号管理和用户门户系统

## 最近变更 (2026-02-20)

### 新增功能 - 签到系统 ✅
**开发团队：** checkin-feature-dev (4人团队协作完成)
- 架构师：系统设计和API规范
- 前端设计师：UI/UX设计和实现
- 后端优化师：数据库和API实现
- 调试专家：测试和bug修复

**实现内容：**
1. **数据库表结构**
   - `checkin_records`: 用户签到记录（user_id, checkin_date, tokens_awarded）
   - `checkin_config`: 管理员配置（min_tokens, max_tokens）
   - UNIQUE约束防止重复签到
   - 索引优化查询性能

2. **用户端功能（8080端口）**
   - 每日签到按钮（渐变紫色，动画效果）
   - 签到状态显示（已签到/未签到）
   - 本次获得tokens展示
   - 连续签到天数统计
   - 本月累计tokens统计
   - 最近7天签到日历视图

3. **管理端功能（8081端口）**
   - 签到配置界面（设置min/max tokens范围）
   - 实时预览（最小、最大、平均奖励）
   - 签到统计数据（今日/总计）

4. **API接口**
   - POST /api/user/checkin - 用户签到
   - GET /api/user/checkin/status - 查询今日状态
   - GET /api/user/checkin/history - 查询历史
   - GET /api/admin/checkin/config - 获取配置
   - POST /api/admin/checkin/config - 更新配置
   - GET /api/admin/checkin/stats - 获取统计

5. **UI美化**
   - 8080用户界面：统一深色主题，紫色主色调
   - 8081管理后台：glassmorphism玻璃态效果
   - 响应式设计，移动端友好

**测试结果：**
- 25个测试全部通过 ✓
- 发现并修复2个关键bug
  - Bug #1: 会话令牌字段名不匹配（user["id"] → user["uid"]）
  - Bug #2: 管理员Cookie名称不一致（统一为"admin_session"）
- 并发安全测试通过
- 边界情况测试通过
- 安全性测试通过

**代码变更：**
- 5个文件修改
- +1246行代码
- -106行代码（优化）

**文档：**
- 架构设计：.claude/checkin-design.md
- 测试报告：.claude/checkin-test-report.md
- 测试代码：.claude/test_checkin.py, test_integration.py

### 用户门户系统
- **8080端口**: 用户门户 (user_app.py) - 面向普通用户
- **8081端口**: 管理后台 (main.py) - 面向超级管理员
- **8082端口**: 备用

### 数据库结构 (portal.db)
- `users`: 用户信息（student_id, password, tokens配额）
- `api_keys`: API密钥（kp-前缀）
- `usage_logs`: 使用记录
- `announcements`: 公告
- `checkin_records`: 签到记录 ✨ 新增
- `checkin_config`: 签到配置 ✨ 新增

### 认证系统
- 管理员: KIRO_ADMIN_USER / KIRO_ADMIN_PASS (默认: shiro/fyz040913)
- 用户: portal_session cookie (包含uid字段)
- 管理员: admin_session cookie
- API Key: kp-xxx格式，通过PortalKeyMiddleware验证

## 技术栈
- FastAPI + uvicorn
- SQLite (WAL模式)
- httpx (异步HTTP客户端)
- Tailwind CSS (前端)
- 原生JavaScript（无框架依赖）

## 关键文件
- `kiro_proxy/main.py`: 主应用入口 (8081)
- `kiro_proxy/portal/user_app.py`: 用户门户 (8080)
- `kiro_proxy/portal/db.py`: 数据库操作
- `kiro_proxy/portal/auth.py`: 认证逻辑
- `kiro_proxy/portal/admin_portal.py`: 管理端API
- `kiro_proxy/web/webui.py`: 管理后台UI

## 团队协作经验
- 使用claude-sonnet-4-5-agentic模型
- 4人团队并行开发
- 架构设计先行，前后端并行
- 完整的测试和bug修复流程
- 文档驱动开发

## 下一步
- 部署到生产环境
- 监控签到功能使用情况
- 根据用户反馈优化UI/UX
