# 漫剧二创自动剪辑 · Manju Drama Auto Re-edit

一套把「官方免费放出的漫剧 / 短剧前几集」加工成可发布二创视频的**半自动工作流**：AI 分析爆点 → 生成带时间码的清单与转写 → 本地 ffmpeg 整集连播粗剪 → 导出可逐段编辑的剪映（CapCut）草稿工程。

核心理念：**无解说、原片台词 + BGM + 字幕金句、整集连播、剧情零跳跃、成片 10 分钟以上**。不依赖解说 TTS，也不需要原始时间码。

> 本项目同时打包为 WorkBuddy Skill（`manju-erchuang`），可在 WorkBuddy 中直接调用。

---

## 功能特性

- **五维爆点模型**：情绪 / 悬念 / 视觉 / 节奏 / 传播，加权打分定位 S/A/B 级片段。
- **无时间码素材可用**：先抽帧 + 音频转写，再让 AI 基于转写与关键帧判断爆点。
- **整集连播模式**：按整集顺序拼接，不碎切、不跳剧情；只保留最后一个「未完待续」。
- **长度自适应**：前几集够 10 分钟就不硬塞后续剧集。
- **剪映工程导出**：生成明文草稿目录，可在剪映中逐段替换素材、加 BGM、改字幕。
- **网页工作台**：单文件 HTML，五维评分器 + 提示词库 + 多剧切换，数据存本地浏览器。
- **云端渲染服务**：Python HTTP 服务，上传素材 → 后台 ffmpeg 渲染 → 下载成片与工程压缩包。

---

## 目录结构

```
manju-erchuang/
├── SKILL.md                     # WorkBuddy 技能定义（含五维模型与完整工作流）
├── scripts/
│   ├── preprocess.py            # 抽帧、提取音频、探测元数据
│   ├── render.py                # 整集连播渲染 + ASS 字幕烧录
│   ├── make_jianying.py         # 生成剪映草稿工程
│   ├── validate_draft.py        # 校验草稿结构与素材引用
│   └── pack_skill.py            # 校验 frontmatter 并打包 Skill zip
├── references/                  # SOP、提示词模板、表格规范、视频分析方法
├── assets/
│   ├── 漫剧二创工作台.html       # 通用版单文件工作台
│   ├── shots.example.json       # 剪辑方案示例
│   ├── render_config.example.json
│   └── 素材库示例.csv
├── web-tool/index.html          # 在线工具箱（评分器 + 提示词库）
└── cloud-render/                # 云端渲染后端示例（见其 README）
```

---

## 快速开始

### 环境要求

- Python 3.8+
- ffmpeg / ffprobe 在 PATH 中（或用 `--ffmpeg` / 环境变量 `FFMPEG` 指定）
- 生成剪映工程需要：`pip install pyJianYingDraft`
- 语音转写使用 WorkBuddy 的音频转写能力；脚本只负责导出 `audio.aac`
- 剪映桌面版（仅生成草稿时需要；草稿目录在剪映设置里查看）

### 工作流

1. **放素材**：把原片按 `第1集.mp4`、`第2集.mp4`… 命名，放进一个 `src/` 目录。
2. **预处理**：`python scripts/preprocess.py --src <素材目录> --out <输出目录>`，得到关键帧、音频和元数据。
3. **AI 分析**：把转写文本和关键帧交给 AI，按 `references/` 里的提示词模板产出 `shots.json`（带时间码的爆点清单）。
4. **评分筛选**：用 `assets/漫剧二创工作台.html` 或 `web-tool/index.html` 按五维模型打分，保留 S/A 级片段，按整集顺序编排。
5. **渲染成片**：`python scripts/render.py --config <shots.json> --out <成片.mp4>`，烧录字幕、保持竖屏 1080×1920。
6. **生成剪映工程**：`python scripts/make_jianying.py --config <shots.json> --drafts <剪映草稿目录>`，导出可编辑草稿。
7. **校验**：`python scripts/validate_draft.py --draft <草稿目录>`。

详细 SOP 见 `references/01_SOP操作手册.md`，提示词见 `references/02_AI提示词模板.md`。

### 五维爆点模型

```
无解说模式总分 = 情绪×0.35 + 悬念×0.30 + 视觉×0.15 + 节奏×0.10 + 传播×0.10
评级：S ≥ 4.2（开头钩子/最高潮） · A 3.5–4.2（主力） · B 3.0–3.5（填充） · < 3.0 淘汰
```

---

## 打包为 Skill

```bash
python scripts/pack_skill.py
```

会校验 `SKILL.md` frontmatter 的 YAML 语法，并生成 `manju-erchuang.zip`（UTF-8 文件名，目录层级符合 WorkBuddy 开放平台规范）。

> 注意：frontmatter 中任何含 `: ` 或 ` #` 的字段值都必须用引号包裹，否则 YAML 会报 `mapping values are not allowed in this context`。

---

## 云端渲染

`cloud-render/main.py` 是一个基于 `ThreadingHTTPServer` 的最小后端示例：multipart 上传 → 任务轮询 → ffmpeg 渲染 → zip 打包素材与工程。具体部署与前端接入见 `cloud-render/README.md`。

---

## 重要声明

- 本工具**不提供任何影视素材**，仅用于对个人合法持有或已获授权的内容进行二次创作。
- 请遵守所在平台的版权规则与「合理使用」范围；商用前务必取得原权利人的授权。
- 请勿将本工具用于批量搬运、侵权传播或违反平台条款的行为。
- 作者不对使用本工具产生的版权纠纷承担责任。

---

## License

[MIT](LICENSE) © 2026 Manju Erchuang Contributors
