# ✅ FAST-P2P 部署检查清单

## 🚀 部署前检查

### 代码质量
- [x] 所有 TypeScript 错误已修复
- [x] 所有 ESLint 警告已处理
- [x] 代码已格式化
- [x] 无 console.log 残留
- [x] 无调试代码

### 功能测试
- [ ] 创建房间功能正常
- [ ] 加入房间功能正常
- [ ] 文件上传功能正常
- [ ] 文件下载功能正常
- [ ] 进度显示准确
- [ ] 二维码生成正常
- [ ] 复制功能正常
- [ ] 拖拽上传正常

### 无障碍测试
- [ ] 键盘导航完整
- [ ] 屏幕阅读器友好
- [ ] 颜色对比度 ≥ 4.5:1
- [ ] 触摸目标 ≥ 44x44px
- [ ] 焦点状态清晰可见
- [ ] ARIA 标签完整

### 性能测试
- [ ] Lighthouse 性能分数 ≥ 90
- [ ] Lighthouse 无障碍分数 ≥ 90
- [ ] 动画流畅 60fps
- [ ] 无内存泄漏
- [ ] 首屏加载 < 3s

### 浏览器兼容性
- [ ] Chrome (最新版)
- [ ] Firefox (最新版)
- [ ] Safari (最新版)
- [ ] Edge (最新版)
- [ ] 移动端 Safari
- [ ] 移动端 Chrome

### 响应式测试
- [ ] 375px (iPhone SE)
- [ ] 768px (iPad)
- [ ] 1024px (iPad Pro)
- [ ] 1440px (Desktop)
- [ ] 横屏模式

### 安全检查
- [ ] HTTPS 配置正确
- [ ] WebSocket 使用 WSS
- [ ] 无敏感信息泄露
- [ ] CSP 策略配置
- [ ] CORS 配置正确

---

## 📦 构建检查

### 构建命令
```bash
# Web 应用
cd apps/web
npm run build

# 中继服务器
cd apps/relay
npm run build
```

### 构建产物
- [ ] `apps/web/dist/` 目录存在
- [ ] `apps/relay/dist/` 目录存在
- [ ] 静态资源已压缩
- [ ] Source maps 已生成
- [ ] 文件大小合理

### 环境变量
```bash
# Web 应用
VITE_RELAY_URL=wss://your-domain.com/ws

# 中继服务器
PORT=3000
NODE_ENV=production
```

---

## 🌐 部署配置

### Nginx 配置示例
```nginx
# Web 应用
server {
    listen 80;
    server_name your-domain.com;
    
    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL 证书
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # 静态文件
    root /path/to/apps/web/dist;
    index index.html;
    
    # SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # WebSocket 代理
    location /ws {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    
    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript 
               application/x-javascript application/xml+rss 
               application/javascript application/json;
}
```

### PM2 配置
```json
{
  "apps": [{
    "name": "fast-p2p-relay",
    "script": "./apps/relay/dist/index.js",
    "instances": 2,
    "exec_mode": "cluster",
    "env": {
      "NODE_ENV": "production",
      "PORT": 3000
    },
    "error_file": "./logs/relay-error.log",
    "out_file": "./logs/relay-out.log",
    "log_date_format": "YYYY-MM-DD HH:mm:ss Z"
  }]
}
```

### Docker 配置
```dockerfile
# Web 应用
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/apps/web/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

## 🔍 部署后验证

### 功能验证
```bash
# 检查 Web 应用
curl https://your-domain.com

# 检查 WebSocket
wscat -c wss://your-domain.com/ws
```

### 性能验证
```bash
# Lighthouse CI
npm install -g @lhci/cli
lhci autorun --collect.url=https://your-domain.com
```

### 监控设置
- [ ] 错误日志监控
- [ ] 性能监控
- [ ] 可用性监控
- [ ] WebSocket 连接监控

---

## 📊 监控指标

### 关键指标
- **可用性**: ≥ 99.9%
- **响应时间**: < 200ms
- **错误率**: < 0.1%
- **WebSocket 连接成功率**: ≥ 99%

### 告警设置
- [ ] 服务器宕机告警
- [ ] 错误率超标告警
- [ ] 响应时间超标告警
- [ ] WebSocket 连接失败告警

---

## 🔄 回滚计划

### 回滚步骤
1. 停止新版本服务
2. 恢复旧版本代码
3. 重启服务
4. 验证功能正常
5. 通知用户

### 回滚命令
```bash
# PM2 回滚
pm2 stop fast-p2p-relay
pm2 delete fast-p2p-relay
git checkout <previous-commit>
npm run build
pm2 start ecosystem.config.json

# Docker 回滚
docker stop fast-p2p-web
docker rm fast-p2p-web
docker run -d --name fast-p2p-web <previous-image>
```

---

## 📝 部署日志

### 部署记录模板
```
部署时间: YYYY-MM-DD HH:mm:ss
部署版本: v2.0
部署人员: [姓名]
部署环境: [生产/测试]

变更内容:
- 无障碍改造完成
- 动画性能优化
- 信任信号增强
- 拖拽交互改进

测试结果:
- 功能测试: ✅ 通过
- 性能测试: ✅ 通过
- 无障碍测试: ✅ 通过

问题记录:
- 无

备注:
- 建议监控 WebSocket 连接稳定性
```

---

## 🎯 部署后任务

### 立即任务
- [ ] 验证所有功能正常
- [ ] 检查错误日志
- [ ] 监控性能指标
- [ ] 通知团队部署完成

### 24小时内
- [ ] 收集用户反馈
- [ ] 监控错误率
- [ ] 检查性能指标
- [ ] 准备热修复（如需要）

### 一周内
- [ ] 分析用户行为数据
- [ ] 收集无障碍反馈
- [ ] 评估性能改进效果
- [ ] 规划下一步优化

---

## 🆘 紧急联系

### 技术支持
- 开发团队: [联系方式]
- 运维团队: [联系方式]
- 产品团队: [联系方式]

### 服务商
- 云服务商: [联系方式]
- CDN 服务商: [联系方式]
- SSL 证书商: [联系方式]

---

## 📚 相关文档

- [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) - 快速参考
- [FINAL_OPTIMIZATION_REPORT.md](./FINAL_OPTIMIZATION_REPORT.md) - 优化报告
- [VISUAL_COMPARISON.md](./VISUAL_COMPARISON.md) - 视觉对比
- [test-checklist.html](./test-checklist.html) - 测试清单

---

**创建时间**: 2026-04-06  
**版本**: v2.0  
**状态**: 准备部署
