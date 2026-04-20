#!/bin/bash
# Flower Shop 部署脚本
# 位置: /opt/flower-shop/deploy.sh

set -e

echo "=== Flower Shop 部署脚本 ==="
echo "时间: $(date)"
echo ""

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[部署]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
error() { echo -e "${RED}[错误]${NC} $1"; exit 1"; }

# 1. 拉取最新代码
log "拉取最新代码..."

cd /opt/flower-shop/backend
git pull origin main
log "后端代码更新完成"

cd /opt/flower-shop/frontend
git pull origin main
log "前端代码更新完成"

cd /opt/flower-shop/admin
git pull origin main
log "管理后台代码更新完成"

# 2. 重建 Docker 容器
log "重建 Docker 容器..."

cd /opt/flower-shop

# 重建后端
log "重建后端容器..."
docker build -t flower-shop-backend:latest ./backend
docker stop flower-backend || true
docker rm flower-backend || true
docker run -d --name flower-backend \
  --network flower-network \
  -p 3457:3457 \
  --restart unless-stopped \
  flower-shop-backend:latest

# 重建前端
log "重建前端容器..."
docker build -t flower-shop-frontend:latest ./frontend
docker stop flower-frontend || true
docker rm flower-frontend || true
docker run -d --name flower-frontend \
  --network flower-network \
  -p 3000:3000 \
  --restart unless-stopped \
  flower-shop-frontend:latest

# 重建管理后台
log "重建管理后台容器..."
docker build -t flower-shop-admin:latest ./admin
docker stop flower-admin || true
docker rm flower-admin || true
docker run -d --name flower-admin \
  --network flower-network \
  -p 3458:80 \
  --restart unless-stopped \
  flower-shop-admin:latest

log "所有容器部署完成！"
echo ""
log "检查容器状态..."
docker ps --filter "name=flower-" --format "table {{.Names}}\t{{.Status}}"
echo ""
log "部署完成！"
