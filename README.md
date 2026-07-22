# gpm-web-admin

Game Push Manager **网页后台**：监测 Windows 服务端（`gpm-server`）与网页服务端（`gpm-web-server`）的运行状态，以及游戏推送条目（整合包 / 模组）的分发情况。

## 监测能力

- **服务端健康**：周期性轮询各服务端 `/api/v1/status`，展示在线状态、运行时长、协议版本
- **存储与计数**：每个服务端的整合包数、模组数、占用空间
- **推送条目**：聚合各服务端 `/api/v1/sync` 返回的整合包 / 模组列表，按游戏分组展示
- **整体视图**：单页仪表盘，一目了然看到 windows-server 与 web-server 的差异

## 架构

- 后端：FastAPI，负责轮询受监测服务端并聚合数据，对外提供 `/api/v1/dashboard` JSON
- 前端：纯静态 HTML + 原生 JS（无构建步骤），由 FastAPI 直接托管，定时刷新
- 配置：通过环境变量 `GPM_WINDOWS_SERVER_URL` / `GPM_WEB_SERVER_URL` 指定监测目标

## 安装与运行

```bash
# 1. 先安装 gpm-common（web-admin 复用其模型）
pip install -e ../gpm-common

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置监测目标
export GPM_WINDOWS_SERVER_URL=http://127.0.0.1:8000
export GPM_WEB_SERVER_URL=http://127.0.0.1:8001

# 4. 运行（默认 0.0.0.0:8080）
python run.py
```

打开浏览器访问 `http://localhost:8080` 即可看到仪表盘。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GPM_HOST` | `0.0.0.0` | 监听地址 |
| `GPM_PORT` | `8080` | 监听端口 |
| `GPM_WINDOWS_SERVER_URL` | `http://127.0.0.1:8000` | Windows 服务端地址 |
| `GPM_WEB_SERVER_URL` | `http://127.0.0.1:8001` | 网页服务端地址 |
| `GPM_MONITOR_INTERVAL` | `10` | 轮询间隔（秒） |
| `GPM_REQUEST_TIMEOUT` | `5` | 单次轮询超时（秒） |
