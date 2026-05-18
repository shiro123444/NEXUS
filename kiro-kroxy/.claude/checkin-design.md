# 签到系统架构设计文档

## 1. 数据库表结构设计

### 1.1 checkin_records 表
记录用户签到历史，确保每天只能签到一次。

```sql
CREATE TABLE IF NOT EXISTS checkin_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    checkin_date TEXT NOT NULL,  -- Format: YYYY-MM-DD
    tokens_awarded INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(user_id, checkin_date)  -- 防止同一天重复签到
);

CREATE INDEX IF NOT EXISTS idx_checkin_user ON checkin_records(user_id);
CREATE INDEX IF NOT EXISTS idx_checkin_date ON checkin_records(checkin_date DESC);
```

**字段说明：**
- `id`: 主键
- `user_id`: 用户ID，外键关联users表
- `checkin_date`: 签到日期（YYYY-MM-DD格式）
- `tokens_awarded`: 本次签到获得的tokens数量
- `created_at`: 记录创建时间
- `UNIQUE(user_id, checkin_date)`: 唯一约束，确保每天只能签到一次

### 1.2 checkin_config 表
存储管理员配置的签到奖励范围（单行表）。

```sql
CREATE TABLE IF NOT EXISTS checkin_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    min_tokens INTEGER NOT NULL DEFAULT 1000,
    max_tokens INTEGER NOT NULL DEFAULT 5000,
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_by TEXT DEFAULT 'admin',
    CHECK (id = 1),  -- 确保只有一行
    CHECK (min_tokens > 0 AND max_tokens >= min_tokens)
);

-- 插入默认配置
INSERT OR IGNORE INTO checkin_config (id, min_tokens, max_tokens)
VALUES (1, 1000, 5000);
```

**字段说明：**
- `id`: 固定为1，确保只有一行配置
- `min_tokens`: 签到最少获得tokens（默认1000）
- `max_tokens`: 签到最多获得tokens（默认5000）
- `updated_at`: 最后更新时间
- `updated_by`: 更新者（管理员用户名）

## 2. API接口设计

### 2.1 用户端API（kiro_proxy/portal/user_app.py）

#### POST /api/user/checkin
用户执行每日签到。

**请求：**
- 认证：需要 `portal_session` cookie
- Body: 无

**响应：**
```json
// 成功
{
  "ok": true,
  "tokens_awarded": 3250,
  "new_total": 5003250,
  "message": "签到成功！获得 3250 tokens"
}

// 今日已签到
{
  "ok": false,
  "error": "今日已签到",
  "already_checked_in": true,
  "tokens_awarded": 3250,
  "checkin_time": "2026-02-20 09:30:15"
}

// 未登录
{
  "error": "请先登录"
}
```

**业务逻辑：**
1. 验证用户登录状态
2. 获取今日日期（YYYY-MM-DD）
3. 检查是否已签到（查询checkin_records）
4. 如果未签到：
   - 从checkin_config获取奖励范围
   - 生成随机tokens: `random.randint(min_tokens, max_tokens)`
   - 开启事务：
     - 插入checkin_records记录
     - 更新users表的total_tokens
   - 提交事务
5. 返回结果

---

#### GET /api/user/checkin/status
获取今日签到状态。

**请求：**
- 认证：需要 `portal_session` cookie

**响应：**
```json
// 已签到
{
  "checked_in": true,
  "tokens_awarded": 3250,
  "checkin_time": "2026-02-20 09:30:15",
  "checkin_date": "2026-02-20"
}

// 未签到
{
  "checked_in": false,
  "can_checkin": true
}
```

---

#### GET /api/user/checkin/history
获取签到历史（最近30天）。

**请求：**
- 认证：需要 `portal_session` cookie
- Query参数：
  - `limit`: 返回记录数（默认30）

**响应：**
```json
{
  "history": [
    {
      "checkin_date": "2026-02-20",
      "tokens_awarded": 3250,
      "created_at": "2026-02-20 09:30:15"
    },
    {
      "checkin_date": "2026-02-19",
      "tokens_awarded": 4100,
      "created_at": "2026-02-19 08:15:22"
    }
  ],
  "total_count": 15,
  "total_tokens_earned": 52300
}
```

---

### 2.2 管理端API（kiro_proxy/portal/admin_portal.py）

#### GET /api/admin/checkin/config
获取签到配置。

**请求：**
- 认证：需要 `portal_admin_session` cookie

**响应：**
```json
{
  "min_tokens": 1000,
  "max_tokens": 5000,
  "updated_at": "2026-02-20 10:00:00",
  "updated_by": "shiro"
}
```

---

#### POST /api/admin/checkin/config
更新签到配置。

**请求：**
- 认证：需要 `portal_admin_session` cookie
- Body:
```json
{
  "min_tokens": 2000,
  "max_tokens": 8000
}
```

**响应：**
```json
// 成功
{
  "ok": true,
  "config": {
    "min_tokens": 2000,
    "max_tokens": 8000,
    "updated_at": "2026-02-20 10:30:00",
    "updated_by": "shiro"
  }
}

// 参数错误
{
  "ok": false,
  "error": "min_tokens 必须大于 0 且小于等于 max_tokens"
}
```

**验证规则：**
- `min_tokens > 0`
- `max_tokens >= min_tokens`
- 两个参数都必须是整数

---

#### GET /api/admin/checkin/stats
获取签到统计数据。

**请求：**
- 认证：需要 `portal_admin_session` cookie
- Query参数：
  - `days`: 统计天数（默认7）

**响应：**
```json
{
  "stats": [
    {
      "date": "2026-02-20",
      "checkin_count": 45,
      "total_tokens_awarded": 156800
    },
    {
      "date": "2026-02-19",
      "checkin_count": 52,
      "total_tokens_awarded": 178300
    }
  ],
  "summary": {
    "total_checkins": 320,
    "total_tokens_awarded": 1125600,
    "avg_tokens_per_checkin": 3518,
    "unique_users": 68
  }
}
```

## 3. 业务逻辑流程

### 3.1 用户签到流程

```
1. 用户点击签到按钮
   ↓
2. 前端调用 POST /api/user/checkin
   ↓
3. 后端验证用户登录状态
   ↓
4. 获取今日日期 (date.today().isoformat())
   ↓
5. 查询 checkin_records 是否存在 (user_id, checkin_date)
   ↓
6. 如果已存在 → 返回"今日已签到"
   ↓
7. 如果不存在：
   a. 查询 checkin_config 获取 (min_tokens, max_tokens)
   b. 生成随机数: tokens = random.randint(min_tokens, max_tokens)
   c. 开启数据库事务：
      - INSERT INTO checkin_records (user_id, checkin_date, tokens_awarded)
      - UPDATE users SET total_tokens = total_tokens + tokens WHERE id = user_id
   d. 提交事务
   ↓
8. 返回签到结果（获得的tokens、新的总额）
   ↓
9. 前端显示签到成功动画和奖励信息
```

### 3.2 管理员配置流程

```
1. 管理员访问配置页面
   ↓
2. 前端调用 GET /api/admin/checkin/config 获取当前配置
   ↓
3. 管理员修改 min_tokens 和 max_tokens
   ↓
4. 前端调用 POST /api/admin/checkin/config 提交新配置
   ↓
5. 后端验证参数合法性
   ↓
6. 更新 checkin_config 表（UPDATE WHERE id = 1）
   ↓
7. 返回更新后的配置
   ↓
8. 前端显示更新成功提示
```

## 4. 实现注意事项

### 4.1 并发安全
- 使用 SQLite WAL 模式（已启用）
- 签到操作使用事务包裹（INSERT + UPDATE）
- UNIQUE 约束防止重复签到

### 4.2 性能优化
- 在 user_id 和 checkin_date 上建立索引
- 签到状态查询可以缓存（基于日期）
- 历史查询限制返回数量（默认30条）

### 4.3 错误处理
- 数据库约束冲突 → "今日已签到"
- 用户未登录 → 401 Unauthorized
- 管理员未登录 → 401 Unauthorized
- 参数验证失败 → 400 Bad Request

### 4.4 时区处理
- 使用 `datetime('now', 'localtime')` 确保使用本地时区
- 签到日期使用 `date.today().isoformat()` 格式化为 YYYY-MM-DD

### 4.5 数据一致性
- 签到操作必须在事务中完成
- 先插入 checkin_records，再更新 users.total_tokens
- 任何一步失败都回滚整个事务

## 5. 集成点

### 5.1 数据库（kiro_proxy/portal/db.py）
需要添加的函数：
- `async def checkin_user(user_id: int) -> dict` - 执行签到
- `async def get_checkin_status(user_id: int, date: str) -> dict` - 查询状态
- `async def get_checkin_history(user_id: int, limit: int) -> list` - 查询历史
- `async def get_checkin_config() -> dict` - 获取配置
- `async def update_checkin_config(min_tokens: int, max_tokens: int, admin: str) -> dict` - 更新配置
- `async def get_checkin_stats(days: int) -> dict` - 获取统计

### 5.2 用户端（kiro_proxy/portal/user_app.py）
需要添加的路由：
- `@app.post("/api/user/checkin")`
- `@app.get("/api/user/checkin/status")`
- `@app.get("/api/user/checkin/history")`

### 5.3 管理端（kiro_proxy/portal/admin_portal.py）
需要添加的路由：
- `@app.get("/api/admin/checkin/config")`
- `@app.post("/api/admin/checkin/config")`
- `@app.get("/api/admin/checkin/stats")`

## 6. 测试清单

### 6.1 功能测试
- [ ] 首次签到成功
- [ ] 重复签到被拒绝
- [ ] tokens正确添加到用户账户
- [ ] 签到历史正确记录
- [ ] 管理员配置更新生效
- [ ] 配置验证规则正确

### 6.2 边界测试
- [ ] 并发签到（多个请求同时到达）
- [ ] 跨日签到（23:59:59 → 00:00:01）
- [ ] min_tokens = max_tokens（固定奖励）
- [ ] 极大值配置（max_tokens = 1000000）
- [ ] 用户配额不足时的处理

### 6.3 安全测试
- [ ] 未登录用户无法签到
- [ ] 普通用户无法访问管理端API
- [ ] SQL注入防护
- [ ] 参数类型验证

### 6.4 性能测试
- [ ] 签到接口响应时间 < 100ms
- [ ] 100并发用户签到
- [ ] 历史查询性能（1000+记录）
- [ ] 统计查询性能

---

**设计完成时间：** 2026-02-20
**设计者：** architect@checkin-feature-dev
**版本：** 1.0
