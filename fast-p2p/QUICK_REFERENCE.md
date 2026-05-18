# 🚀 FAST-P2P 快速参考指南

## 📁 项目结构

```
FAST-P2P/
├── apps/
│   ├── web/                    # React Web 应用
│   │   ├── src/
│   │   │   ├── routes/
│   │   │   │   └── home-page.tsx    # 主页组件 ⭐
│   │   │   └── styles.css           # 全局样式 ⭐
│   │   ├── index.html
│   │   └── vite.config.ts
│   └── relay/                  # WebSocket 中继服务器
├── src/
│   └── p2p/
│       └── web.html            # 旧版独立 HTML ⭐
├── packages/
│   └── shared/                 # 共享代码
├── UI_FIX_PLAN.md             # 修复计划
├── UI_FIX_SUMMARY.md          # 修复总结
├── DESIGN_ITERATION_V2.md     # 迭代优化
├── FINAL_OPTIMIZATION_REPORT.md # 最终报告
├── VISUAL_COMPARISON.md       # 视觉对比
└── test-checklist.html        # 测试清单
```

---

## 🎨 设计系统速查

### 颜色变量
```css
/* 基础颜色 */
--bg: #ece8e1;                    /* 背景色 */
--ink: #0c0c0c;                   /* 主文本 */
--ink-soft: rgba(12, 12, 12, 0.72);  /* 次要文本 */
--ink-dim: rgba(12, 12, 12, 0.65);   /* 辅助文本 (4.5:1 对比度) */

/* 状态颜色 */
--success: #22C55E;               /* 绿色 - 成功/安全 */
--warning: #F59E0B;               /* 橙色 - 等待 */
--error: #EF4444;                 /* 红色 - 错误 */
--info: #3B82F6;                  /* 蓝色 - 进行中 */

/* 玻璃拟态 */
--panel: rgba(255, 255, 255, 0.2);
--panel-strong: rgba(255, 255, 255, 0.34);
--panel-soft: rgba(255, 255, 255, 0.12);
```

### 动画曲线
```css
--curve-out: cubic-bezier(0.22, 1, 0.36, 1);      /* 弹出效果 */
--curve-smooth: cubic-bezier(0.2, 0.8, 0.2, 1);   /* 平滑过渡 */
```

### 阴影
```css
--shadow: 0 28px 80px rgba(20, 20, 20, 0.08);     /* 主阴影 */
--shadow-soft: 0 16px 42px rgba(20, 20, 20, 0.06); /* 柔和阴影 */
```

---

## 🔧 常用组件类名

### 按钮
```css
.action-button                    /* 基础按钮 */
.action-button-primary            /* 主按钮 (黑色) */
.action-button-secondary          /* 次按钮 (白色) */
.action-button-ghost              /* 幽灵按钮 */
.text-button                      /* 文本按钮 */
.text-button-inline               /* 内联文本按钮 */
```

### 状态徽章
```css
.badge                            /* 基础徽章 */
.badge-transferring               /* 传输中 (蓝色) */
.badge-pending                    /* 等待中 (橙色) */
.badge-done                       /* 已完成 (绿色) */
.badge-error                      /* 错误 (红色) */
```

### 表单
```css
.text-field                       /* 文本输入框容器 */
.text-field input                 /* 输入框 */
.text-field span                  /* 标签 */
```

### 进度条
```css
.progress-track                   /* 进度条轨道 */
.progress-fill                    /* 进度条填充 */
```

### 上传区域
```css
.upload-surface                   /* 上传区域 */
.upload-surface.drag-over         /* 拖拽悬停状态 */
.upload-surface.disabled          /* 禁用状态 */
```

### 空状态
```css
.empty-state                      /* 空状态容器 */
.empty-state-icon                 /* 空状态图标 */
.empty-state-text                 /* 空状态文本 */
.empty-state-hint                 /* 空状态提示 */
```

---

## 🎯 关键优化点

### 1. 动画性能
```css
/* ✅ 推荐 - 使用 transform */
.button:hover {
  transform: scale(1.02);
  will-change: transform;
}

/* ❌ 避免 - 导致布局抖动 */
.button:hover {
  transform: translateY(-2px);
}
```

### 2. 颜色对比度
```css
/* ✅ 推荐 - 4.5:1 对比度 */
color: rgba(12, 12, 12, 0.65);

/* ❌ 避免 - 对比度不足 */
color: rgba(12, 12, 12, 0.46);
```

### 3. 触摸目标
```css
/* ✅ 推荐 - 至少 44x44px */
.button {
  min-height: 50px;
  min-width: 50px;
}
```

### 4. 焦点状态
```css
/* ✅ 推荐 - 清晰可见 */
.button:focus-visible {
  outline: 3px solid rgba(12, 12, 12, 0.8);
  outline-offset: 3px;
}
```

---

## 🔍 ARIA 属性速查

### 按钮
```tsx
<button aria-label="创建新房间">create</button>
```

### 输入框
```tsx
<label htmlFor="room-code-input">
  <span>room code</span>
  <input 
    id="room-code-input"
    aria-label="输入房间码"
  />
</label>
```

### 进度条
```tsx
<div 
  role="progressbar" 
  aria-valuenow={progress} 
  aria-valuemin={0} 
  aria-valuemax={100}
  aria-label="传输进度"
/>
```

### 实时更新
```tsx
<span aria-live="polite" aria-atomic="true">
  {statusMessage}
</span>
```

### 加载状态
```tsx
<div aria-busy="true" aria-label="加载中">
  {skeleton}
</div>
```

### 空状态
```tsx
<div role="status" aria-label="暂无数据">
  {emptyState}
</div>
```

---

## 🧪 测试命令

### 开发服务器
```bash
# Web 应用
cd apps/web
npm run dev
# http://localhost:5173/

# 中继服务器
cd apps/relay
npm run dev
# ws://localhost:3000/ws
```

### 构建
```bash
# Web 应用
cd apps/web
npm run build

# 中继服务器
cd apps/relay
npm run build
```

### 测试
```bash
# 打开测试清单
# 浏览器打开: test-checklist.html

# Chrome Lighthouse
# DevTools > Lighthouse > Accessibility
```

---

## 📝 常见任务

### 添加新按钮
```tsx
<button 
  className="action-button action-button-primary"
  onClick={handleClick}
  aria-label="按钮描述"
>
  按钮文本
</button>
```

### 添加新状态徽章
```tsx
<span className="badge badge-done">
  完成
</span>
```

### 添加进度条
```tsx
<div 
  className="progress-track"
  role="progressbar"
  aria-valuenow={percent}
  aria-valuemin={0}
  aria-valuemax={100}
>
  <div 
    className="progress-fill" 
    style={{ width: `${percent}%` }}
  />
</div>
```

### 添加拖拽上传
```tsx
const [isDragging, setIsDragging] = useState(false);

<label 
  className={`upload-surface${isDragging ? " drag-over" : ""}`}
  onDragOver={(e) => {
    e.preventDefault();
    setIsDragging(true);
  }}
  onDragLeave={() => setIsDragging(false)}
  onDrop={(e) => {
    e.preventDefault();
    setIsDragging(false);
    handleFile(e.dataTransfer.files[0]);
  }}
>
  {/* 上传区域内容 */}
</label>
```

---

## 🐛 常见问题

### Q: 动画卡顿？
A: 检查是否使用了 `transform` 和 `will-change`

### Q: 颜色对比度不足？
A: 使用 WebAIM Contrast Checker 验证，确保至少 4.5:1

### Q: 键盘导航不工作？
A: 检查 `tabIndex` 和 `onKeyDown` 事件

### Q: 屏幕阅读器无法识别？
A: 添加 `aria-label` 和 `role` 属性

### Q: 移动端按钮太小？
A: 确保 `min-height` 和 `min-width` 至少 44px

---

## 📚 相关资源

### 文档
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)
- [MDN Web Docs](https://developer.mozilla.org/)

### 工具
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- [axe DevTools](https://www.deque.com/axe/devtools/)
- [Chrome Lighthouse](https://developers.google.com/web/tools/lighthouse)

### 图标库
- [Heroicons](https://heroicons.com/)
- [Lucide](https://lucide.dev/)
- [Simple Icons](https://simpleicons.org/)

---

## 🎓 最佳实践

### 性能
- ✅ 使用 `transform` 和 `opacity` 做动画
- ✅ 添加 `will-change` 提示浏览器
- ✅ 避免动画触发布局重排

### 无障碍
- ✅ 所有交互元素添加 ARIA 标签
- ✅ 确保键盘可访问
- ✅ 颜色对比度至少 4.5:1

### 用户体验
- ✅ 提供清晰的状态反馈
- ✅ 使用颜色编码区分状态
- ✅ 添加拖拽视觉反馈

### 代码质量
- ✅ 使用语义化 HTML
- ✅ 遵循 React 最佳实践
- ✅ 保持代码简洁清晰

---

## 🔄 更新日志

### v2.0 (2026-04-06)
- ✅ 完整的无障碍改造
- ✅ 动画性能优化
- ✅ 信任信号增强
- ✅ 拖拽交互改进
- ✅ 状态徽章系统
- ✅ Toast 通知系统

### v1.0 (初始版本)
- 基础功能实现
- 玻璃拟态设计
- P2P 文件传输

---

**维护者**: OpenCode AI Assistant  
**最后更新**: 2026-04-06  
**版本**: v2.0
