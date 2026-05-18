# 🎬 FAST-P2P 落地页重构计划

## 🎯 设计目标

### 核心定位
**展示型落地页** - 不是功能界面，是产品展示页面

### 设计原则
1. **全宽布局** - 充分利用宽屏空间
2. **视频背景** - 动态背景 + 玻璃材质前景
3. **滚动视差** - 垂直滚动，元素横向进入
4. **排版优先** - 文字层次清晰，可读性强

---

## 📐 布局结构

### 1. Hero Section (100vh)
```
┌─────────────────────────────────────────┐
│  [视频背景 - 循环播放]                    │
│                                         │
│  ┌───────────────────────────────┐     │
│  │  [玻璃材质容器]                │     │
│  │                               │     │
│  │  PREACH                       │     │
│  │  端到端加密文件传输             │     │
│  │                               │     │
│  │  [CTA 按钮]                   │     │
│  └───────────────────────────────┘     │
│                                         │
└─────────────────────────────────────────┘
```

**动画**:
- 标题从左侧滑入 (translateX(-100px) → 0)
- 副标题从右侧滑入 (translateX(100px) → 0)
- CTA 从下方淡入 (opacity 0 → 1, translateY(50px) → 0)

---

### 2. Features Section (全宽)
```
┌─────────────────────────────────────────┐
│                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │ 🔐      │  │ ⚡      │  │ 🛡️      │ │
│  │ AES-256 │  │ 零延迟  │  │ 零知识  │ │
│  │ 加密    │  │ 传输    │  │ 架构    │ │
│  └─────────┘  └─────────┘  └─────────┘ │
│                                         │
└─────────────────────────────────────────┘
```

**动画**:
- 卡片从左侧依次进入 (stagger 延迟 100ms)
- 滚动到视口时触发

---

### 3. How It Works (交替布局)
```
┌─────────────────────────────────────────┐
│                                         │
│  ┌──────────┐          ┌──────────┐    │
│  │ 图片/动画 │  ←───→  │ 文字说明  │    │
│  └──────────┘          └──────────┘    │
│                                         │
│  ┌──────────┐          ┌──────────┐    │
│  │ 文字说明  │  ←───→  │ 图片/动画 │    │
│  └──────────┘          └──────────┘    │
│                                         │
└─────────────────────────────────────────┘
```

**动画**:
- 左侧内容从左进入
- 右侧内容从右进入
- 交替布局增加空间感

---

### 4. CTA Section (全宽)
```
┌─────────────────────────────────────────┐
│  [视频背景 - 模糊]                        │
│                                         │
│  ┌───────────────────────────────┐     │
│  │  准备好开始了吗？              │     │
│  │                               │     │
│  │  [立即体验] [了解更多]         │     │
│  └───────────────────────────────┘     │
│                                         │
└─────────────────────────────────────────┘
```

---

## 🎨 视觉设计

### 视频背景
```css
.video-background {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  object-fit: cover;
  z-index: -1;
  filter: blur(0px); /* Hero 清晰 */
}

.video-background.blurred {
  filter: blur(20px); /* 其他区域模糊 */
}
```

### 玻璃材质
```css
.glass-container {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}
```

---

## 🎬 滚动动画

### 视差效果
```javascript
// 背景视频慢速移动
video.style.transform = `translateY(${scrollY * 0.5}px)`;

// 前景内容正常速度
content.style.transform = `translateY(${scrollY * 1}px)`;
```

### 横向进入动画
```css
/* 从左进入 */
@keyframes slideInLeft {
  from {
    opacity: 0;
    transform: translateX(-100px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

/* 从右进入 */
@keyframes slideInRight {
  from {
    opacity: 0;
    transform: translateX(100px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
```

---

## 📱 响应式设计

### 断点
```css
/* 移动端 */
@media (max-width: 768px) {
  .hero-title { font-size: 48px; }
  .features-grid { grid-template-columns: 1fr; }
}

/* 平板 */
@media (min-width: 769px) and (max-width: 1024px) {
  .hero-title { font-size: 72px; }
  .features-grid { grid-template-columns: repeat(2, 1fr); }
}

/* 桌面 */
@media (min-width: 1025px) {
  .hero-title { font-size: 96px; }
  .features-grid { grid-template-columns: repeat(3, 1fr); }
}

/* 宽屏 */
@media (min-width: 1440px) {
  .container { max-width: 1400px; }
  .hero-title { font-size: 120px; }
}
```

---

## ✍️ 排版系统

### 字体层次
```css
/* 超大标题 - Hero */
.hero-title {
  font-size: clamp(48px, 8vw, 120px);
  font-weight: 700;
  line-height: 0.9;
  letter-spacing: -0.05em;
}

/* 大标题 - Section */
.section-title {
  font-size: clamp(32px, 5vw, 64px);
  font-weight: 600;
  line-height: 1.1;
  letter-spacing: -0.03em;
}

/* 副标题 */
.subtitle {
  font-size: clamp(18px, 2vw, 24px);
  font-weight: 400;
  line-height: 1.5;
  letter-spacing: 0;
}

/* 正文 */
.body-text {
  font-size: clamp(16px, 1.5vw, 18px);
  font-weight: 400;
  line-height: 1.6;
  max-width: 65ch; /* 可读性 */
}
```

---

## 🚀 实施步骤

### Phase 1: 布局重构
- [ ] 移除当前的固定宽度容器
- [ ] 实现全宽布局
- [ ] 添加响应式断点

### Phase 2: 视频背景
- [ ] 添加视频元素
- [ ] 实现玻璃材质覆盖层
- [ ] 优化视频加载

### Phase 3: 滚动动画
- [ ] 实现 Intersection Observer
- [ ] 添加横向进入动画
- [ ] 实现视差效果

### Phase 4: 排版优化
- [ ] 重新设计字体层次
- [ ] 优化行高和字间距
- [ ] 确保可读性

---

## 🎯 成功标准

- ✅ 全宽布局，无留白
- ✅ 视频背景流畅播放
- ✅ 滚动动画有空间感
- ✅ 文字排版清晰易读
- ✅ 响应式完美适配
- ✅ 性能流畅 60fps

---

**开始时间**: 2026-04-06  
**预计完成**: 2小时
