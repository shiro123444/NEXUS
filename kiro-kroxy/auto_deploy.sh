#!/bin/bash

# 自动部署脚本 - 每分钟检测 git 更新并自动拉取重启服务
# 日志文件路径
LOG_FILE="/root/Kiro-Kroxy/auto_deploy.log"
PROJECT_DIR="/root/Kiro-Kroxy"
VENV_PATH="$PROJECT_DIR/venv/bin/python"

# cron 环境 PATH 很精简，显式补齐常用系统路径
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 检查虚拟环境
if [ ! -f "$VENV_PATH" ]; then
    log "错误: 虚拟环境不存在于 $VENV_PATH"
    exit 1
fi

cd "$PROJECT_DIR" || exit 1

# 检测可用的端口查询工具（优先 ss，次选 lsof）
SS_BIN=$(command -v ss || true)
LSOF_BIN=$(command -v lsof || true)

# 获取当前提交哈希
CURRENT_HASH=$(git rev-parse HEAD)
log "当前提交: $CURRENT_HASH"

# 拉取远程更新
log "检查远程更新..."
git fetch origin main 2>&1 | tee -a "$LOG_FILE"

# 获取远程提交哈希
REMOTE_HASH=$(git rev-parse origin/main)
log "远程提交: $REMOTE_HASH"

# 比较本地和远程
if [ "$CURRENT_HASH" != "$REMOTE_HASH" ]; then
    log "=========================================="
    log "检测到更新！开始拉取并重启服务..."
    log "=========================================="
    
    # 拉取更新
    log "执行 git pull..."
    git pull origin main 2>&1 | tee -a "$LOG_FILE"
    
    if [ $? -ne 0 ]; then
        log "错误: git pull 失败"
        exit 1
    fi
    
    log "代码更新成功"
    
    # 查找并停止现有服务（按端口号查找，避免进程名不匹配）
    log "停止现有服务..."

    stop_port() {
        local PORT=$1
        local PID

        if [ -n "$SS_BIN" ]; then
            PID=$($SS_BIN -tlnp "sport = :$PORT" 2>/dev/null | awk 'NR>1 {match($0, /pid=([0-9]+)/, a); if(a[1]) print a[1]}')
        elif [ -n "$LSOF_BIN" ]; then
            PID=$($LSOF_BIN -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1)
        else
            PID=""
            log "警告: 未找到 ss/lsof，无法按端口查找进程"
        fi

        if [ -n "$PID" ]; then
            log "停止 $PORT 端口服务 (PID: $PID)"
            kill -15 "$PID" 2>/dev/null
            sleep 2
            if ps -p "$PID" > /dev/null 2>&1; then
                log "强制停止 $PORT 端口服务"
                kill -9 "$PID" 2>/dev/null
            fi
            log "$PORT 端口服务已停止"
        else
            log "未找到 $PORT 端口服务进程"
        fi
    }

    stop_port 8081
    stop_port 8080
    
    # 等待端口释放
    sleep 3
    
    # 重启服务
    log "启动服务..."

    # 启动 8081 端口服务（主代理）
    log "启动 8081 端口服务（主代理）..."
    nohup "$VENV_PATH" "$PROJECT_DIR/run.py" --no-ui 8081 >> "$PROJECT_DIR/service_8081.log" 2>&1 &
    PID_NEW_8081=$!
    log "8081 端口服务已启动 (PID: $PID_NEW_8081)"

    # 启动 8080 端口服务（用户门户）
    log "启动 8080 端口服务（用户门户）..."
    cd "$PROJECT_DIR" && nohup "$VENV_PATH" -m uvicorn kiro_proxy.portal.user_app:app --host 0.0.0.0 --port 8080 >> "$PROJECT_DIR/service_8080.log" 2>&1 &
    PID_NEW_8080=$!
    log "8080 端口服务已启动 (PID: $PID_NEW_8080)"
    
    # 等待服务启动
    sleep 5
    
    # 验证服务是否正常运行
    if ps -p "$PID_NEW_8081" > /dev/null; then
        log "✓ 8081 端口服务运行正常"
    else
        log "✗ 8081 端口服务启动失败"
    fi
    
    if ps -p "$PID_NEW_8080" > /dev/null; then
        log "✓ 8080 端口服务运行正常"
    else
        log "✗ 8080 端口服务启动失败"
    fi
    
    log "=========================================="
    log "部署完成！"
    log "=========================================="
else
    log "无更新，跳过部署"
fi

log "检查完成"
log ""
