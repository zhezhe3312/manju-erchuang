# 云端渲染服务（可选）

`main.py` 是一个最小可用的 Python HTTP 服务示例，用于在有 ffmpeg 的服务器上异步完成渲染：

- `POST /api/upload` — multipart 上传素材与 `shots.json`
- `GET /api/status?id=<task_id>` — 轮询任务状态
- `GET /api/result?id=<task_id>` — 下载 zip（成片 + 素材 + 剪映工程）

## 运行

```bash
pip install -r requirements.txt
python main.py
```

服务默认监听本地端口，生产环境请放在反向代理之后，并自行加上鉴权、并发限制与存储清理。

## 前端

本仓库**不包含线上部署版前端页面**：那份页面内联了特定平台的云服务配置（endpoint / publishableKey / sharecode），出于安全考虑不予公开。

如要自行接入，可参考：

- `../web-tool/index.html` — 纯前端工具箱（评分器 + 提示词库），无云服务依赖
- `../SKILL.md` — 完整的本地工作流说明

你可以在自己的页面上直接调用本服务的 API，或用任意对象存储 + 队列替换它。
