# -*- coding: utf-8 -*-
"""
步骤3 · 生成剪映草稿工程：把 shots.json 方案变成一个可逐段编辑的剪映草稿。

依赖：pip install pyJianYingDraft（测试版本 0.3.1）

用法：
  python make_jianying.py --project <项目目录> --draft-root <剪映草稿目录> --name <草稿名>

参数：
  --project     项目目录（含 src/ 和 shots.json）
  --draft-root  剪映草稿根目录（在剪映设置→草稿位置里查，Windows 通常是 JianyingPro Drafts）
  --name        草稿名（剪映列表里显示的名字）
  --fps         帧率，默认30
  --width/--height  画幅，默认 1080x1920
  --gold-sec    金句闪现秒数，默认5

重要 · 剪映 10.x 草稿不显示的解决：
  本脚本生成的是明文草稿。剪映只在【启动时】扫描一次草稿目录，
  且新版剪映会把打开的草稿加密接管。若列表看不到：
    1) 完全退出剪映（含右下角托盘图标 → 退出）
    2) 重新打开剪映，草稿即出现
  草稿本身有效（scripts/validate_draft.py 可校验），问题几乎都是"剪映没重启"。
"""
import os, sys, json, shutil, argparse, time

try:
    import pyJianYingDraft as d
    from pyJianYingDraft import (
        VideoMaterial, VideoSegment, TextSegment,
        Timerange, TrackType, TrackSpec, TextStyle, TextBorder, ClipSettings, SEC
    )
except ImportError:
    print("缺少依赖，请先运行: pip install pyJianYingDraft")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="漫剧二创 · 生成剪映草稿")
    ap.add_argument("--project", required=True)
    ap.add_argument("--draft-root", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--gold-sec", type=float, default=5.0)
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    src_dir = os.path.join(project, "src")
    shots = json.load(open(os.path.join(project, "shots.json"), encoding="utf-8"))
    print(f"=== {args.name} | {len(shots)} 段 ===")

    # 校验原片
    vdur = {}
    for sh in shots:
        ep = int(sh["ep"])
        p = os.path.join(src_dir, f"第{ep}集.mp4")
        if ep not in vdur:
            if not os.path.exists(p):
                print("缺少原片:", p); sys.exit(1)
            vdur[ep] = VideoMaterial(p).duration
    print("原片校验通过，共", len(vdur), "集")

    folder = d.DraftFolder(args.draft_root)
    script = folder.create_draft(args.name, args.width, args.height, args.fps,
                                 maintrack_adsorb=True, allow_replace=True)
    vtrack = script.append_track(TrackSpec(TrackType.video, "主视频"))
    ttrack = script.append_track(TrackSpec(TrackType.text, "金句字幕"))

    style = TextStyle(size=9.0, bold=True, color=(1, 1, 1), align=1)
    border = TextBorder(color=(0, 0, 0), alpha=1.0, width=50.0)
    clip = ClipSettings(transform_y=-0.78)

    for sh in shots:
        ep = int(sh["ep"])
        src_path = os.path.join(src_dir, f"第{ep}集.mp4")
        src_start = int(round(sh["src_sec"] * SEC))
        src_dur = int(round(sh["duration"] * SEC))
        tl_start = int(round(sh["tl_start"] * SEC))
        tl_dur = int(round(sh["duration"] * SEC))
        if src_start + src_dur > vdur[ep]:
            src_dur = vdur[ep] - src_start
            tl_dur = src_dur
        if src_dur <= 0:
            continue
        script.add_segment(
            VideoSegment(src_path, Timerange(tl_start, tl_dur),
                         source_timerange=Timerange(src_start, src_dur)),
            vtrack)
        sub = sh.get("subtitle", "")
        gd = int(min(args.gold_sec, sh["duration"] - 0.5) * SEC)
        if sub and gd > 0:
            script.add_segment(
                TextSegment(sub, Timerange(tl_start + int(0.5 * SEC), gd),
                            style=style, border=border, clip_settings=clip),
                ttrack)

    script.save()
    draft_path = os.path.join(args.draft_root, args.name)

    # 补全 meta 关键字段（新版剪映列表依赖这些字段）
    meta_path = os.path.join(draft_path, "draft_meta_info.json")
    if os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path, encoding="utf-8"))
            now = int(time.time() * 1000)
            meta["draft_name"] = args.name
            meta["draft_root_path"] = args.draft_root
            meta["draft_fold_path"] = draft_path
            meta["draft_new_version"] = "1"
            meta.setdefault("tm_draft_create", now)
            meta.setdefault("tm_draft_modified", now)
            json.dump(meta, open(meta_path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        except Exception as e:
            print("meta 更新跳过（可能是加密格式，无妨）:", e)

    # 备份
    backup = os.path.join(project, "剪映工程备份", args.name)
    if os.path.exists(backup):
        shutil.rmtree(backup)
    shutil.copytree(draft_path, backup)

    try:
        folder.load_template(args.name)
        print("校验：草稿可被读回 ✓")
    except Exception as e:
        print("校验读回：", e)

    print(f"\n草稿已生成：{draft_path}")
    print("若剪映列表看不到：完全退出剪映（含托盘）后重新打开即可。")


if __name__ == "__main__":
    main()
