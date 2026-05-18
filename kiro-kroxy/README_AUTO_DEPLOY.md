# 自动部署系统说明

## 功能概述

已配置自动部署系统，每分钟检测 GitHub 仓库更新，如有新提交则自动拉取并重启服务。

## 文件说明

- **auto_deploy.sh**: 自动部署脚本
- **auto_deploy.log**: 详细部署日志
- **cron.log**: Cron 任务执行日志

## 工作流程

1. 每分钟执行一次检查
2. 对比本地和远程 commit hash
3. 如果检测到更新：
   - 执行 `git pull`
   - 停止现有的 8080 和 8081 端口服务
   - 使用虚拟环境重启两个服务
   - 记录详细日志

## 查看日志

```bash
# 查看自动部署日志
tail -f /root/Kiro-Kroxy/auto_deploy.log

# 查看 cron 执行日志
tail -f /root/Kiro-Kroxy/cron.log

# 查看服务运行日志
tail -f /root/Kiro-Kroxy/service_8080.log
tail -f /root/Kiro-Kroxy/service_8081.log
```

## 手动执行

```bash
# 手动触发部署检查
bash /root/Kiro-Kroxy/auto_deploy.sh
```

## 管理 Cron 任务

```bash
# 查看当前定时任务
crontab -l

# 编辑定时任务
crontab -e

# 删除自动部署任务
crontab -l | grep -v "auto_deploy.sh" | crontab -
```

## 本地开发流程

1. 在本地克隆仓库并开发
2. 提交并推送到 GitHub
3. 服务器会在 1 分钟内自动检测并部署
4. 查看日志确认部署成功

## 注意事项

- 虚拟环境路径: `/root/Kiro-Kroxy/venv/bin/python`
- 服务会自动重启，可能有几秒钟的服务中断
- 如果部署失败，检查 `auto_deploy.log` 查看错误信息
- Git 冲突需要手动解决
