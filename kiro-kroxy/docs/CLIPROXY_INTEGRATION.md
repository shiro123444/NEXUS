# CLIProxy 管理界面集成指南

## 概述

本文档说明 [cliproxy](https://github.com/erik6293/Cli-Proxy-API-PLUS-Management) 管理界面如何与 Kiro-Kroxy 配额系统联动，以及如何在 CLI Proxy API Plus 环境中集成 Kiro 账号管理。

## 项目关系

### cliproxy 是什么

cliproxy 是 [CLI Proxy API Management Center](https://github.com/router-for-me/Cli-Proxy-API-Management-Center) 的增强版 Fork，主要增强功能包括：

- **Kiro (AWS CodeWhisperer) 配额显示** - 查看 Kiro 账号的基础配额和免费试用配额
- **GitHub Copilot 配额显示** - 查看 Copilot 账号的 Chat/Completions/Premium 配额
- **认证文件页面配额刷新** - 在认证文件管理页面直接刷新配额信息

### Kiro-Kroxy 是什么

Kiro-Kroxy 是一个独立的 Kiro API 反向代理服务器，核心功能包括：

- 多账号轮询和负载均衡
- Token 自动刷新和健康检查
- 三种协议支持（OpenAI/Anthropic/Gemini）
- 完整的工具调用和流式响应支持
- 内置 Web UI 管理界面

### 联动关系

```
┌─────────────────┐         ┌──────────────────────┐         ┌─────────────────┐
│   cliproxy      │         │  CLI Proxy API Plus  │         │   Kiro-Kroxy    │
│  (Web UI)       │◄────────│  (代理服务器)         │         │  (独立代理)      │
│                 │  管理API │                      │         │                 │
│  - 配额显示     │         │  - 认证文件管理       │         │  - 多账号轮询   │
│  - 账号管理     │         │  - /v0/management/*  │         │  - Token刷新    │
│  - 日志查看     │         │  - 转发配额查询       │         │  - 配额管理     │
└─────────────────┘         └──────────────────────┘         └─────────────────┘
         │                           │                                │
         │                           │                                │
         └───────────────────────────┴────────────────────────────────┘
                        通过 /v0/management/api-call 查询配额
                                      │
                                      ▼
                        ┌──────────────────────────────┐
                        │  AWS CodeWhisperer API       │
                        │  codewhisperer.amazonaws.com │
                        │  - GetUsageLimits            │
                        └──────────────────────────────┘
```

**关键点**：
- cliproxy 不直接与 Kiro-Kroxy 通信
- cliproxy 通过 CLI Proxy API Plus 的管理 API 查询配额
- CLI Proxy API Plus 需要管理 Kiro 认证文件才能提供配额查询功能
- Kiro-Kroxy 是独立的代理服务，有自己的 Web UI

## 配额查询机制

### API 端点

cliproxy 使用 CLI Proxy API Plus 的统一管理 API：

```
POST /v0/management/api-call
Authorization: Bearer <MANAGEMENT_KEY>
Content-Type: application/json
```

### Kiro 配额查询请求

```json
{
  "auth_index": "<KIRO_AUTH_INDEX>",
  "method": "POST",
  "url": "https://codewhisperer.us-east-1.amazonaws.com",
  "header": {
    "Content-Type": "application/x-amz-json-1.0",
    "x-amz-target": "AmazonCodeWhispererService.GetUsageLimits",
    "Authorization": "Bearer $TOKEN$"
  },
  "data": "{\"origin\": \"AI_EDITOR\", \"resourceType\": \"AGENTIC_REQUEST\"}"
}
```

**参数说明**：
- `auth_index` - Kiro 认证文件的索引（从 `/v0/management/auth-files` 获取）
- `$TOKEN$` - 占位符，CLI Proxy API Plus 会自动替换为实际的 accessToken
- `x-amz-target` - AWS 服务目标，指定调用 GetUsageLimits 方法

### 响应格式

成功响应包含两层 JSON：

```json
{
  "status_code": 200,
  "header": { ... },
  "body": "<JSON字符串，需要再次解析>"
}
```

解析 `body` 后得到实际配额数据：

```json
{
  "nextDateReset": 1772323200.0,
  "subscriptionInfo": {
    "subscriptionTitle": "KIRO FREE"
  },
  "usageBreakdownList": [{
    "resourceType": "CREDIT",
    "usageLimitWithPrecision": 50.0,
    "currentUsageWithPrecision": 10.5,
    "freeTrialInfo": {
      "freeTrialStatus": "ACTIVE",
      "usageLimitWithPrecision": 500.0,
      "currentUsageWithPrecision": 21.48,
      "freeTrialExpiry": 1772553426.991
    }
  }]
}
```

## cliproxy 技术实现

### 核心文件结构

```
cliproxy/src/
├── components/quota/
│   └── quotaConfigs.ts          # 配额配置和获取逻辑
├── utils/quota/
│   ├── parsers.ts               # 数据解析函数
│   ├── constants.ts             # API 常量定义
│   └── validators.ts            # 数据验证
├── pages/
│   ├── QuotaPage.tsx            # 配额管理页面
│   └── AuthFilesPage.tsx        # 认证文件页面（含配额刷新）
└── types/
    └── quota.ts                 # TypeScript 类型定义
```

### 关键实现代码

#### 1. 配额获取函数 (quotaConfigs.ts)

```typescript
const fetchKiroQuota = async (
  file: AuthFileItem,
  t: TFunction
): Promise<KiroQuotaData> => {
  const authIndex = normalizeAuthIndexValue(file['auth_index'] ?? file.authIndex);
  if (!authIndex) {
    throw new Error(t('kiro_quota.missing_auth_index'));
  }

  // 调用 CLI Proxy API Plus 的 api-call 端点
  const result = await apiCallApi.request({
    authIndex,
    method: 'POST',
    url: KIRO_QUOTA_URL,  // AWS CodeWhisperer API
    header: { ...KIRO_REQUEST_HEADERS },
    data: KIRO_REQUEST_BODY,
  });

  // 检查 HTTP 状态码
  if (result.statusCode < 200 || result.statusCode >= 300) {
    const errorPayload = parseKiroErrorPayload(result.body ?? result.bodyText);
    if (errorPayload?.reason === 'TEMPORARILY_SUSPENDED') {
      throw createStatusError(t('kiro_quota.suspended'), result.statusCode);
    }
    throw createStatusError(getApiCallErrorMessage(result), result.statusCode);
  }

  // 解析配额数据
  const payload = parseKiroQuotaPayload(result.body ?? result.bodyText);
  if (!payload) {
    throw new Error(t('kiro_quota.empty'));
  }

  // 提取订阅信息
  const subscriptionTitle = normalizeStringValue(
    payload.subscriptionInfo?.subscriptionTitle
  );

  // 提取基础配额
  const usageBreakdown = payload.usageBreakdownList?.[0];
  let baseQuota: KiroBaseQuota | null = null;
  let freeTrialQuota: KiroFreeTrialQuota | null = null;

  if (usageBreakdown) {
    const limit = normalizeNumberValue(usageBreakdown.usageLimitWithPrecision);
    const used = normalizeNumberValue(usageBreakdown.currentUsageWithPrecision);
    const resetTime = normalizeNumberValue(
      usageBreakdown.nextDateReset ?? payload.nextDateReset
    );

    if (limit !== null && used !== null && resetTime !== null) {
      baseQuota = { used, limit, resetTime };
    }

    // 提取免费试用配额
    const freeTrialInfo = usageBreakdown.freeTrialInfo;
    if (freeTrialInfo) {
      const trialLimit = normalizeNumberValue(freeTrialInfo.usageLimitWithPrecision);
      const trialUsed = normalizeNumberValue(freeTrialInfo.currentUsageWithPrecision);
      const trialExpiry = normalizeNumberValue(freeTrialInfo.freeTrialExpiry);
      const trialStatus = normalizeStringValue(freeTrialInfo.freeTrialStatus);

      if (trialLimit !== null && trialUsed !== null &&
          trialExpiry !== null && trialStatus) {
        freeTrialQuota = {
          used: trialUsed,
          limit: trialLimit,
          expiry: trialExpiry,
          status: trialStatus,
        };
      }
    }
  }

  return { subscriptionTitle, baseQuota, freeTrialQuota };
};
```

#### 2. UI 渲染函数

```typescript
const renderKiroItems = (
  quota: KiroQuotaState,
  t: TFunction,
  helpers: QuotaRenderHelpers
): ReactNode => {
  const { styles: styleMap, QuotaProgressBar } = helpers;
  const { createElement: h, Fragment } = React;
  const nodes: ReactNode[] = [];

  // 显示订阅类型（KIRO FREE / KIRO POWER）
  if (quota.subscriptionTitle) {
    nodes.push(
      h('div', { key: 'subscription', className: styleMap.codexPlan },
        h('span', { className: styleMap.codexPlanLabel },
          t('kiro_quota.subscription_label')),
        h('span', { className: styleMap.codexPlanValue },
          quota.subscriptionTitle)
      )
    );
  }

  // 显示基础配额
  if (quota.baseQuota) {
    const { used, limit, resetTime } = quota.baseQuota;
    const remaining = Math.max(0, limit - used);
    const percent = limit > 0 ? Math.round((remaining / limit) * 100) : 0;
    const resetLabel = formatKiroResetTime(resetTime);  // M/D HH:MM 格式

    nodes.push(
      h('div', { key: 'base', className: styleMap.quotaRow },
        h('div', { className: styleMap.quotaRowHeader },
          h('span', { className: styleMap.quotaModel },
            t('kiro_quota.base_quota')),
          h('div', { className: styleMap.quotaMeta },
            h('span', { className: styleMap.quotaPercent }, `${percent}%`),
            h('span', { className: styleMap.quotaAmount },
              `${remaining.toFixed(1)}/${limit}`),
            h('span', { className: styleMap.quotaReset }, resetLabel)
          )
        ),
        h(QuotaProgressBar, {
          percent,
          highThreshold: 60,
          mediumThreshold: 20
        })
      )
    );
  }

  // 显示免费试用配额（仅 FREE 用户）
  if (quota.freeTrialQuota) {
    const { used, limit, expiry, status } = quota.freeTrialQuota;
    const remaining = Math.max(0, limit - used);
    const percent = limit > 0 ? Math.round((remaining / limit) * 100) : 0;
    const isActive = status.toUpperCase() === 'ACTIVE';
    const statusLabel = isActive ?
      t('kiro_quota.trial_active') :
      t('kiro_quota.trial_expired');
    const expiryLabel = formatKiroResetTime(expiry);

    nodes.push(
      h('div', { key: 'trial', className: styleMap.quotaRow },
        h('div', { className: styleMap.quotaRowHeader },
          h('span', { className: styleMap.quotaModel },
            `${t('kiro_quota.free_trial')} (${statusLabel})`),
          h('div', { className: styleMap.quotaMeta },
            h('span', { className: styleMap.quotaPercent }, `${percent}%`),
            h('span', { className: styleMap.quotaAmount },
              `${remaining.toFixed(1)}/${limit}`),
            h('span', { className: styleMap.quotaReset }, expiryLabel)
          )
        ),
        h(QuotaProgressBar, {
          percent,
          highThreshold: 60,
          mediumThreshold: 20
        })
      )
    );
  }

  return h(Fragment, null, ...nodes);
};
```

#### 3. 配置对象

```typescript
export const KIRO_CONFIG: QuotaConfig<KiroQuotaState, KiroQuotaData> = {
  type: 'kiro',
  i18nPrefix: 'kiro_quota',
  filterFn: (file) => isKiroFile(file) && !isDisabledAuthFile(file),
  fetchQuota: fetchKiroQuota,
  storeSelector: (state) => state.kiroQuota,
  storeSetter: 'setKiroQuota',
  buildLoadingState: () => ({
    status: 'loading',
    subscriptionTitle: null,
    baseQuota: null,
    freeTrialQuota: null,
  }),
  buildSuccessState: (data) => ({
    status: 'success',
    subscriptionTitle: data.subscriptionTitle,
    baseQuota: data.baseQuota,
    freeTrialQuota: data.freeTrialQuota,
  }),
  buildErrorState: (message, status) => ({
    status: 'error',
    subscriptionTitle: null,
    baseQuota: null,
    freeTrialQuota: null,
    error: message,
    errorStatus: status,
  }),
  cardClassName: styles.kiroCard,
  controlsClassName: styles.kiroControls,
  controlClassName: styles.kiroControl,
  gridClassName: styles.kiroGrid,
  renderQuotaItems: renderKiroItems,
};
```

### 时间格式化

```typescript
const formatKiroResetTime = (timestamp: number | undefined): string => {
  if (!timestamp) return '-';
  const date = new Date(timestamp * 1000);  // Unix 时间戳转毫秒
  if (isNaN(date.getTime())) return '-';

  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');

  return `${month}/${day} ${hours}:${minutes}`;  // 格式：2/21 14:30
};
```

## 在 Kiro-Kroxy 中的应用

虽然 Kiro-Kroxy 是独立的代理服务，但可以参考 cliproxy 的实现来增强自己的配额管理功能：

### 1. 配额查询 API

Kiro-Kroxy 已经实现了配额查询功能（`kiro_proxy/core/usage.py`），可以直接调用 AWS CodeWhisperer API：

```python
async def get_kiro_quota(credential: KiroCredentials) -> dict:
    """查询 Kiro 账号配额"""
    url = "https://codewhisperer.us-east-1.amazonaws.com"
    headers = {
        "Content-Type": "application/x-amz-json-1.0",
        "x-amz-target": "AmazonCodeWhispererService.GetUsageLimits",
        "Authorization": f"Bearer {credential.access_token}"
    }
    data = {
        "origin": "AI_EDITOR",
        "resourceType": "AGENTIC_REQUEST"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
        return response.json()
```

### 2. Web UI 集成

Kiro-Kroxy 的 Web UI (`kiro_proxy/web/webui.py`) 可以添加配额显示功能：

```python
@app.get("/api/accounts/{account_id}/quota")
async def get_account_quota(account_id: str):
    """获取账号配额信息"""
    account = state.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        quota_data = await get_kiro_quota(account.credential)
        return {
            "subscription": quota_data.get("subscriptionInfo", {}).get("subscriptionTitle"),
            "base_quota": extract_base_quota(quota_data),
            "free_trial": extract_free_trial(quota_data)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 3. 配额监控

可以在后台任务中定期检查配额：

```python
async def monitor_quotas():
    """定期监控所有账号的配额"""
    while True:
        for account in state.accounts.values():
            try:
                quota = await get_kiro_quota(account.credential)
                usage_breakdown = quota.get("usageBreakdownList", [{}])[0]

                used = usage_breakdown.get("currentUsageWithPrecision", 0)
                limit = usage_breakdown.get("usageLimitWithPrecision", 0)

                # 配额不足时发出警告
                if limit > 0 and (used / limit) > 0.9:
                    logger.warning(
                        f"Account {account.id} quota low: "
                        f"{used:.1f}/{limit} ({(used/limit)*100:.1f}%)"
                    )

            except Exception as e:
                logger.error(f"Failed to check quota for {account.id}: {e}")

        await asyncio.sleep(3600)  # 每小时检查一次
```

## 错误处理

### 常见错误及处理

#### 1. 账号被封禁 (TEMPORARILY_SUSPENDED)

```json
{
  "__type": "com.amazon.aws.codewhisperer#AccessDeniedException",
  "message": "Your User ID (d-xxx) temporarily is suspended...",
  "reason": "TEMPORARILY_SUSPENDED"
}
```

**处理方式**：
- cliproxy：显示友好的错误提示 "账号已被临时封禁"
- Kiro-Kroxy：自动禁用该账号，切换到其他可用账号

#### 2. Token 过期

```json
{
  "status_code": 401,
  "body": "Unauthorized"
}
```

**处理方式**：
- 触发 Token 自动刷新机制
- 刷新成功后重试配额查询
- 刷新失败则标记账号为不可用

#### 3. 网络错误

**处理方式**：
- 实现重试机制（最多 3 次）
- 使用指数退避策略
- 记录详细的错误日志

## 最佳实践

### 1. 配额查询频率

- **不要过于频繁**：AWS API 有速率限制
- **推荐频率**：每 5-10 分钟查询一次
- **用户触发**：允许用户手动刷新配额

### 2. 缓存策略

```typescript
// cliproxy 使用 Zustand 状态管理
interface QuotaStore {
  kiroQuota: Record<string, KiroQuotaState>;
  setKiroQuota: (updater: QuotaUpdater<Record<string, KiroQuotaState>>) => void;
  clearQuotaCache: () => void;
}

// 缓存有效期：5 分钟
const CACHE_TTL = 5 * 60 * 1000;
```

### 3. 错误提示

- 使用国际化 (i18n) 支持多语言错误提示
- 区分不同类型的错误（网络错误、认证错误、配额错误）
- 提供可操作的建议（如"请稍后重试"、"请联系管理员"）

### 4. 性能优化

- 并行查询多个账号的配额
- 使用连接池复用 HTTP 连接
- 实现请求去重（避免重复查询同一账号）

## 开发调试

### 1. 本地测试 cliproxy

```bash
cd /home/shiro/Projects/cliproxy
npm install
npm run dev
```

访问 `http://localhost:5173`，连接到 CLI Proxy API Plus 实例。

### 2. 模拟 API 响应

创建测试数据：

```typescript
// 测试用的 Kiro 配额响应
const mockKiroQuota = {
  nextDateReset: Math.floor(Date.now() / 1000) + 86400,
  subscriptionInfo: {
    subscriptionTitle: "KIRO FREE"
  },
  usageBreakdownList: [{
    resourceType: "CREDIT",
    usageLimitWithPrecision: 50.0,
    currentUsageWithPrecision: 25.5,
    freeTrialInfo: {
      freeTrialStatus: "ACTIVE",
      usageLimitWithPrecision: 500.0,
      currentUsageWithPrecision: 150.0,
      freeTrialExpiry: Math.floor(Date.now() / 1000) + 2592000
    }
  }]
};
```

### 3. 查看网络请求

使用浏览器开发者工具查看：
- Network 标签：查看 `/v0/management/api-call` 请求
- Console 标签：查看解析后的配额数据
- React DevTools：查看组件状态

## 参考资料

### 相关文档

- [cliproxy 项目](https://github.com/erik6293/Cli-Proxy-API-PLUS-Management)
- [CLI Proxy API Plus](https://github.com/router-for-me/CLIProxyAPI)
- [Kiro-Kroxy README](../README.md)
- [Kiro 配额 API 文档](https://github.com/erik6293/Cli-Proxy-API-PLUS-Management/blob/main/kiro_quota.md)
- [Copilot 配额 API 文档](https://github.com/erik6293/Cli-Proxy-API-PLUS-Management/blob/main/copilot_quota.md)

### Git 提交历史

cliproxy 关键提交：

```bash
7dbe0d5 feat: 添加 Kiro 和 GitHub Copilot 配额显示支持
7ac0342 fix: 修复编译产物版本号不正确的问题
9d0b352 feat: 支持版本号递增，避免 tag 重复
```

Kiro-Kroxy 关键提交：

```bash
75e0f4c feat: port kiro.rs-fork improvements to Kiro-Kroxy
341de04 confirmed: claude-sonnet-4.6 works on both accounts
af5a128 feat: add Claude Sonnet 4.6 model support
```

## 总结

cliproxy 和 Kiro-Kroxy 虽然是独立的项目，但通过 CLI Proxy API Plus 的管理 API 可以实现配额查询的联动：

1. **cliproxy** 提供了完整的 Web UI 来显示 Kiro 配额信息
2. **Kiro-Kroxy** 可以参考 cliproxy 的实现来增强自己的配额管理功能
3. 两者都使用相同的 AWS CodeWhisperer API 来查询配额
4. 核心技术是通过 `/v0/management/api-call` 端点代理 AWS API 请求

如果需要在 Kiro-Kroxy 中实现类似的配额显示功能，可以直接参考 cliproxy 的实现代码，特别是：
- `src/components/quota/quotaConfigs.ts` - 配额获取逻辑
- `src/utils/quota/parsers.ts` - 数据解析函数
- `src/pages/QuotaPage.tsx` - UI 渲染组件
