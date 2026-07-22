# gpm-web-admin

Game Push Manager **网页后台**：被动接收各端主动上报的心跳，监测 Windows 服务端（`gpm-server`）、网页服务端（`gpm-web-server`）与 Windows 客户端（`gpm-client`）的运行状态及游戏推送条目。

## 监测模型：Push（被动接收）

> **本后台不轮询任何服务端。** 各端启动后通过 `gpm_common.Reporter` 后台线程，每隔固定间隔主动向本服务 `POST /api/v1/report` 上报 `Heartbeat`。后台仅在内存中维护最近一次心跳，超过 `GPM_STALE_SECONDS`（默认 30s）未收到上报即判定为离线。

这样设计的好处：
- 后台无需知道各端的访问凭证或防火墙打通入站方向
- 各端可在 NAT/内网中运行，只要能访问后台的 `/api/v1/report` 即可
- 后台无状态、轻量，仅暴露一个接收接口 + 一个聚合查询接口

## 监测能力

- **状态指示灯系统**：每个上报端带绿/黄/红/灰灯，仪表盘顶部展示「系统总体灯」（取所有端最严重者）；每个卡片左侧边框与名称前圆点反映灯色，并展示灯色原因。灯色含义：
  - 🟢 绿灯 健康（服务端磁盘占用 < 85% 且无累积错误）
  - 🟡 黄灯 降级（服务端磁盘占用 85%~95%）
  - 🔴 红灯 异常（服务端磁盘占用 ≥ 95%、存储目录不可访问、累计错误过多，或离线超时）
  - ⚪ 灰灯 未知（该端未上报灯色）
- **服务端健康**：在线状态、运行时长、整合包/模组数量、存储占用、累计错误数、距上次上报时间、累计上报次数
- **客户端状态**：在线状态、已安装整合包列表、上次同步时间、累计上报次数
- **推送条目**：服务端上报时携带 modpacks/mods 列表，后台按游戏分组聚合展示
- **整体视图**：单页仪表盘，分别展示服务端组与客户端组

## 架构

- 后端：FastAPI
  - `POST /api/v1/report`：接收 Heartbeat，存入内存 `ReportStore`
  - `GET /api/v1/dashboard`：聚合所有上报，返回仪表盘 JSON
- 前端：纯静态 HTML + 原生 JS（无构建步骤），每 5 秒拉取一次 dashboard

## 安装与运行

```bash
# 1. 先安装 gpm-common
pip install -e ../gpm-common

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行（默认 0.0.0.0:8080）
python run.py
```

打开浏览器访问 `http://localhost:8080`。

各端通过环境变量 `GPM_ADMIN_URL=http://<本后台地址>:8080` 指定上报目标。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GPM_HOST` | `0.0.0.0` | 监听地址 |
| `GPM_PORT` | `8080` | 监听端口 |
| `GPM_STALE_SECONDS` | `30` | 心跳过期阈值（秒），超过则判定上报端离线 |

## Heartbeat 载荷

见 `gpm-common` 的 `gpm_common/heartbeat.py`：

```json
{
  "reporter_id": "uuid 或稳定名称",
  "kind": "windows-server | web-server | client",
  "name": "展示名",
  "base_url": "服务端可被外部访问的地址（客户端无）",
  "status": "online",
  "protocol_version": "1.0.0",
  "sent_at": "2026-07-22T09:00:00Z",
  "metrics": {
    "modpack_count": 3,
    "mod_count": 12,
    "storage_used_bytes": 524288000,
    "uptime_seconds": 3600,
    "modpacks": [...],
    "mods": [...],
    "installed_modpacks": [...]
  }
}
```
