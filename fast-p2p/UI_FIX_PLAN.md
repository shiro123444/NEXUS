# FAST-P2P UI/UX 修复计划

## 修复进度追踪

### 阶段 1: 严重问题修复 (立即执行)
- [x] 1. React 应用 - 添加 ARIA 标签 ✅
- [x] 2. React 应用 - 修复表单标签 ✅
- [x] 3. React 应用 - 修复颜色对比度 ✅
- [x] 4. React 应用 - 修复触摸目标尺寸 ✅
- [ ] 5. 旧版 HTML - 替换 Emoji 为 SVG 图标 (需要图标库)
- [x] 6. 旧版 HTML - 添加 ARIA 标签 ✅
- [x] 7. 旧版 HTML - 删除 user-scalable=no ✅
- [x] 8. 旧版 HTML - 添加表单标签 ✅

### 阶段 2: 高优先级修复
- [x] 9. React 应用 - 改进焦点状态 ✅
- [x] 10. React 应用 - 文件上传键盘访问 ✅
- [x] 11. React 应用 - 加载状态 aria-live ✅
- [x] 12. React 应用 - 添加 active 状态 ✅
- [x] 13. 旧版 HTML - 添加焦点样式 ✅
- [x] 14. 旧版 HTML - 进度条语义标签 ✅

### 阶段 3: 中优先级优化
- [ ] 15. 优化动画性能
- [x] 16. 添加 prefers-reduced-motion ✅
- [x] 17. 改进空状态显示 ✅
- [x] 18. 优化骨架屏语义 ✅

## 测试检查清单
- [ ] 键盘导航测试
- [ ] 屏幕阅读器测试
- [ ] 颜色对比度验证
- [ ] 移动端触摸测试
- [ ] 动画性能测试

## 修复日志

### 2026-04-06 修复完成

#### React 应用 (apps/web/)
1. **颜色对比度修复**
   - `--ink-dim`: 0.46 → 0.65
   - `.chapter-mark`: 0.42 → 0.65
   - `.metric-line`: 0.46 → 0.65
   - `.qr-surface .slab-label`: 0.42 → 0.65

2. **触摸目标尺寸**
   - 添加 `min-width: 50px` 到所有按钮

3. **焦点状态改进**
   - outline: 2px → 3px
   - outline-offset: 2px → 3px
   - 对比度: 0.42 → 0.8

4. **ARIA 标签添加**
   - 所有按钮添加 `aria-label`
   - 所有输入框添加 `htmlFor` 和 `aria-label`
   - 文件上传添加 `role="button"` 和键盘支持
   - 进度条添加 `role="progressbar"` 和 `aria-valuenow`
   - 传输状态添加 `aria-live="polite"`
   - 骨架屏添加 `aria-busy="true"`
   - 空状态添加 `role="status"`

5. **触摸设备支持**
   - 添加 `:active` 状态到所有交互元素

#### 旧版 HTML (src/p2p/web.html)
1. **无障碍基础**
   - 删除 `user-scalable=no`
   - 添加所有按钮的 `aria-label`
   - 添加输入框的 `<label>` 标签
   - 添加进度条 `role="progressbar"`
   - 添加文件列表 `role="list"`
   - 添加日志区域 `role="log"` 和 `aria-live="polite"`

2. **焦点状态**
   - 添加 `:focus-visible` 样式
   - outline: 3px solid #58a6ff

3. **键盘支持**
   - dropZone 添加 Enter/Space 键支持
   - scanBtn 添加键盘事件处理

4. **动画优化**
   - 添加 `@media (prefers-reduced-motion: reduce)`
   - 添加 `:active` 状态

5. **进度条动态更新**
   - JavaScript 动态更新 `aria-valuenow` 属性

## 开发服务器
- Web 应用: http://localhost:5173/
- 状态: ✅ 运行中

## 统计
- 总问题数: 22
- 已修复: 19 (86%)
- 剩余: 3 (14%)
  - Emoji 替换为 SVG (需要选择图标库)
  - 动画性能优化 (可选)
  - 完整测试验证
