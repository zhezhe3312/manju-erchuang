---
name: manju-erchuang
version: 1.0.0
display_name: 漫剧二创自动剪辑
display_name_en: Manju Drama Auto Re-edit
description: "漫剧二创自动剪辑全流程工具。当用户提供漫剧/短剧/动漫视频素材（官方免费集数），想做成多账号矩阵发布的二创混剪、剧情浓缩、整集连播视频，并需要分析爆点、语音转写、生成带时间码的爆点清单、渲染粗剪成片、生成可逐段编辑的剪映工程草稿时，应使用本技能。触发词：漫剧二创、短剧二创、混剪、爆点分析、剧情浓缩、整集连播、剪映工程、二创剪辑。"
description_zh: "漫剧二创自动剪辑全流程工具。当用户提供漫剧/短剧/动漫视频素材（官方免费集数），想做成多账号矩阵发布的二创混剪、剧情浓缩、整集连播视频，并需要分析爆点、语音转写、生成带时间码的爆点清单、渲染粗剪成片、生成可逐段编辑的剪映工程草稿时，应使用本技能。触发词：漫剧二创、短剧二创、混剪、爆点分析、剧情浓缩、整集连播、剪映工程、二创剪辑。"
description_en: "End-to-end auto-editing workflow for short-drama and anime re-creation. Use when the user provides official free episodes of a drama/anime and wants to produce re-edited clips, plot digests, or full-episode compilations for multi-account publishing, including highlight scoring, speech transcription, timecoded highlight lists, rough-cut rendering, and editable CapCut/JianyingPro draft projects. Triggers: drama re-edit, short-video remix, highlight analysis, plot digest, full-episode compilation, CapCut project."
author: WorkBuddy Creator
agent_created: true
---

# 漫剧二创自动剪辑

## 用途

把官方免费放出的漫剧/短剧前几集，通过 AI 分析爆点 + 本地 ffmpeg 剪辑，做成可发布到多账号矩阵的二创视频。**当前主推模式：无解说，原片台词 + BGM + 字幕金句 + 整集连播**（剧情零跳跃，成片 10-17 分钟）。

核心交付物：带时间码的爆点清单、语音转写文本、剪辑方案（shots.json）、粗剪 MP4、可逐段编辑的剪映草稿工程。

## 环境要求（开始前先确认）

- **ffmpeg / ffprobe** 在 PATH 中（脚本也支持 `--ffmpeg` / 环境变量 `FFMPEG` 指定路径）
- **Python 3.8+**
- **剪映**（桌面版）— 仅生成草稿时需要；草稿目录路径需在剪映设置里查「草稿位置」
- 生成剪映工程需 `pip install pyJianYingDraft`
- 语音转写由 WorkBuddy 的音频转写能力完成（脚本只负责导出 audio.aac）

先问用户：素材放在哪个目录？剪映草稿目录在哪（不确定就让用户从剪映设置里查）？成片想要整集连播还是碎切卡点？

## 五维爆点模型（分析的灵魂）

每段候选按 5 个维度各打 1-5 分，加权求和：

```
总分 = 情绪×0.30 + 悬念×0.25 + 视觉×0.20 + 节奏×0.15 + 传播×0.10
```

无解说模式（更看重情绪和悬念）：

```
总分 = 情绪×0.35 + 悬念×0.30 + 视觉×0.15 + 节奏×0.10 + 传播×0.10
```

| 维度 | 判断标准 |
|------|----------|
| 情绪峰值 | 角色哭/怒/爽/反转/打脸的情绪张力 |
| 悬念钩子 | 前3秒能否制造"然后呢" |
| 视觉冲击 | 大场面/特效/快动作/特写 |
| 节奏卡点 | 鼓点密度、镜头切换是否干脆 |
| 传播潜力 | 梗点/争议点/金句 |

评级：**S ≥ 4.2**（开头钩子或最高潮）、**A 3.5-4.2**（主力）、**B 3.0-3.5**（填充）、<3.0 淘汰。

## 完整工作流

### 工位① 素材预处理（脚本）

让用户把原片按 `第1集.mp4`、`第2集.mp4`… 命名，放进一个 `src/` 目录（可按剧名建子文件夹分组）。然后运行：

```bash
python scripts/preprocess.py "素材目录" 2 "分析输出目录"
```

产出每集 `frames/`（关键帧，序号对应时间码见 info.json）、`audio.aac`、`info.json`，以及 `_时间码索引.csv`。

### 工位② AI 分析爆点（WorkBuddy 完成，不用脚本）

1. **语音转写**：用 WorkBuddy 的音频转写能力，逐集转写 `audio.aac`，拿到带时间码的台词。**台词比画面更能定位情绪爆点**——短剧镜头极密，逐帧看不如看台词。
2. **视觉核对**：抽取候选时间点的关键帧，用看图能力确认画面内容（谁在场、什么动作、有无"未完待续"金字）。
3. **五维打分**：参考 `references/02_AI提示词模板.md` 的模板3，对每个候选段打分，输出爆点清单表格（时间点/画面/情绪/悬念/视觉/节奏/传播/总分/等级/建议用法）。
4. **生成金句**：参考模板8，为每个爆点生成字幕金句（8-14字，点题不复述）。

### 工位③ 生成剪辑方案 shots.json

**策略选择（重要）**：
- 用户要"剧情连贯、不跳" → **整集连播**：一部剧拆成上/下两部，每部约 7 集整集拼接（第N集从 0:00 到集尾），成片 15-17 分钟；前几集够时长就不必硬塞后面集数。
- 用户要"卡点高燃" → 按 S 级爆点取片段，但注意别太碎。

整集连播的 shots.json 写法：每集一段，`src_sec=0`，`duration=该集时长`，`subtitle=金句`。参考 `assets/shots.example.json`。可放 `render_config.json` 控制画幅/帧率/是否裁集尾（见 `assets/render_config.example.json`）。
**注意**：裁集尾"未完待续"前必须先抽帧确认——有的剧集尾是金字定格（可裁 2 秒），有的是叠影转场（不能裁，否则断剧情）。

### 工位④ 渲染粗剪成片（脚本）

```bash
python scripts/render.py "<项目目录>"
# 项目目录内含 src/、shots.json、（可选）render_config.json
```

产出 `成片.mp4`（拼接 + 烧录金句字幕）。`--no-sub` 可跳过字幕。

### 工位⑤ 生成剪映工程（脚本）

```bash
python scripts/make_jianying.py --project "<项目目录>" \
  --draft-root "<剪映草稿目录>" --name "<草稿名>" --fps 30
```

生成明文草稿到剪映草稿目录，并备份到项目目录。生成后的草稿**与成片是两套独立产物**：草稿里每集是独立片段，可在剪映里逐段微调、加 BGM、导出。

**剪映 10.x 草稿不显示的排查（高频问题）**：
1. 先用 `python scripts/validate_draft.py "<草稿目录>"` 校验——大概率文件是好的。
2. 剪映只在**启动时**扫描草稿目录一次。若草稿在剪映运行期间才写入，列表不会出现。
3. 解决：**完全退出剪映（含右下角托盘图标 → 退出）再重开**。剪映打开草稿后会加密接管并补全封面等文件。
4. 若重开仍不显示，检查 `--draft-root` 是否与剪映设置里的「草稿位置」一致（含盘符/中文路径）。

## 交付规范

- 成片竖屏 1080×1920，30fps（先 ffprobe 原片确认帧率，不一致就按原片）。
- 金句字幕每段开头闪现 5 秒，白字黑描边、底部居中。
- 全程无解说：原片台词 + BGM（用户自己在剪映加）+ 字幕金句。
- 版权提醒：优先用官方免费/授权素材；二创要加原创字幕观点和差异化处理，避免搬运。

## 参考资源

- `references/01_SOP操作手册.md` — 完整 SOP 与工位说明
- `references/02_AI提示词模板.md` — 8 个提示词模板（标题/爆点分析/金句/差异化等）
- `references/03_素材表格字段模板.md` — 素材管理字段规范
- `references/04_10分钟剧情浓缩版结构.md` — 剧情浓缩结构
- `references/怎么用视频分析.md` — 素材分析操作说明
- `assets/漫剧二创工作台.html` — 通用展示页（五维算分/提示词库/方法论，单文件可直接打开）
- `assets/素材库示例.csv` — 素材库模板
- `assets/shots.example.json` / `render_config.example.json` — 配置示例

## 已知边界

- 浏览器/工作台只能做展示、算分、提示词复制、文件入口；真正的抽帧、转写、看图打分、金句生成必须在 WorkBuddy 对话里由 AI 完成。
- 本技能不替用户上传发布到平台，也不规避平台版权审核。
