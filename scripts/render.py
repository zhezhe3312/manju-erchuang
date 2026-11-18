# -*- coding: utf-8 -*-
"""
步骤2 · 通用渲染脚本：按 shots.json 方案截取原片 → 拼接 → 烧录金句字幕 → 成片。

shots.json 方案格式（由 AI 分析后生成，或参考 assets/shots.example.json）：
[
  {
    "no": 1,
    "ep": 1,                  # 集号，对应 src_dir 里的 第N集.mp4
    "src_sec": 0,             # 原片内起始秒
    "duration": 78,           # 片段时长秒
    "subtitle": "这一巴掌，替我女儿打",  # 段头金句（可空）
    "tl_start": 0,            # 时间轴起始秒
    "tl_end": 78              # 时间轴结束秒
  },
  ...
]

用法：
  python render.py --project <项目目录> [--ffmpeg ffmpeg] [--no-sub]

项目目录结构：
  <project>/
    src/            原片（第1集.mp4、第2集.mp4 ...）
    shots.json      剪辑方案
    （运行后生成）segments/  临时片段
    （运行后生成）_merged.mp4
    （运行后生成）成片.mp4

参数可通过命令行或项目目录下的 render_config.json 提供：
  {"src_dir":"src","out_name":"成片.mp4","fps":30,"width":1080,"height":1920,
   "gold_sec":5,"font":"Microsoft YaHei","font_size":64,"tail_cut":0}
"""
import os, sys, json, subprocess, shutil, argparse


def load_config(project):
    cfg = {"src_dir": "src", "out_name": "成片.mp4", "fps": 30,
           "width": 1080, "height": 1920, "gold_sec": 5.0,
           "font": "Microsoft YaHei", "font_size": 64, "tail_cut": 0}
    p = os.path.join(project, "render_config.json")
    if os.path.exists(p):
        cfg.update(json.load(open(p, encoding="utf-8")))
    return cfg


def parse_plan(project, cfg):
    shots = json.load(open(os.path.join(project, "shots.json"), encoding="utf-8"))
    # 重新计算时间轴，保证连贯无重叠
    cursor = 0.0
    for i, sh in enumerate(shots, 1):
        sh.setdefault("no", i)
        sh["tl_start"] = round(cursor, 2)
        sh["tl_end"] = round(cursor + sh["duration"], 2)
        cursor += sh["duration"]
    json.dump(shots, open(os.path.join(project, "shots.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return shots, cursor


def write_ass(project, shots, cfg):
    W, H, font = cfg["width"], cfg["height"], cfg["font"]
    ass = ["[Script Info]", "ScriptType: v4.00+",
           f"PlayResX: {W}", f"PlayResY: {H}",
           "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           f"Style: Gold,{font},{cfg['font_size']},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,4,1,2,60,60,300,1", "",
           "[Events]",
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    def tstr(x):
        h = int(x // 3600); mi = int((x % 3600) // 60); s = x % 60
        return f"{h:d}:{mi:02d}:{s:05.2f}"

    for sh in shots:
        sub = sh.get("subtitle", "")
        if not sub:
            continue
        gs = sh["tl_start"] + 0.5
        ge = min(sh["tl_end"], gs + cfg["gold_sec"])
        if ge <= gs:
            continue
        g = str(sub).replace("{", "(").replace("}", ")").replace("\n", " ")
        ass.append(f"Dialogue: 0,{tstr(gs)},{tstr(ge)},Gold,,0,0,0,,{g}")
    ass_path = os.path.join(project, "金句字幕.ass")
    open(ass_path, "w", encoding="utf-8").write("\n".join(ass))
    return ass_path


def main():
    ap = argparse.ArgumentParser(description="漫剧二创 · 通用渲染")
    ap.add_argument("project", help="项目目录（含 src/ 和 shots.json）")
    ap.add_argument("--ffmpeg", default=os.environ.get("FFMPEG", "ffmpeg"))
    ap.add_argument("--ffprobe", default=os.environ.get("FFPROBE", "ffprobe"))
    ap.add_argument("--no-sub", action="store_true", help="不烧录字幕")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    cfg = load_config(project)
    ffmpeg, ffprobe = args.ffmpeg, args.ffprobe
    src_dir = os.path.join(project, cfg["src_dir"])
    tmp_dir = os.path.join(project, "segments")
    W, H, FPS = cfg["width"], cfg["height"], cfg["fps"]

    shots, total = parse_plan(project, cfg)
    print(f"共 {len(shots)} 段，成片约 {int(total//60)}分{int(total%60):02d}秒")

    os.makedirs(tmp_dir, exist_ok=True)
    fail = []
    for sh in shots:
        src = os.path.join(src_dir, f"第{sh['ep']}集.mp4")
        if not os.path.exists(src):
            print("  缺少原片:", src); fail.append(sh["no"]); continue
        out = os.path.join(tmp_dir, f"{sh['no']:03d}.mp4")
        cmd = [ffmpeg, "-y", "-v", "error", "-ss", str(sh["src_sec"]), "-i", src,
               "-t", str(sh["duration"]),
               "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
               "-movflags", "+faststart", out]
        r = subprocess.run(cmd)
        if r.returncode != 0 or not os.path.exists(out):
            fail.append(sh["no"])
    print(f"截取完成：成功 {len(shots)-len(fail)}/{len(shots)}", ("失败:"+str(fail)) if fail else "")
    if fail:
        print("存在失败片段，请检查原片路径后续时长。")

    segs = [os.path.join(tmp_dir, f"{sh['no']:03d}.mp4") for sh in shots
            if os.path.exists(os.path.join(tmp_dir, f"{sh['no']:03d}.mp4"))]
    lf = os.path.join(project, "concat_list.txt")
    open(lf, "w", encoding="utf-8").write(
        "".join("file '" + p.replace("\\", "/") + "'\n" for p in segs))
    merged = os.path.join(project, "_merged.mp4")
    print("拼接中...")
    if subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0",
                       "-i", lf, "-c", "copy", merged]).returncode != 0:
        print("拼接失败"); sys.exit(1)

    final = os.path.join(project, cfg["out_name"])
    if args.no_sub:
        shutil.copy(merged, final)
    else:
        ass = write_ass(project, shots, cfg)
        ass_ff = ass.replace("\\", "/").replace(":", "\\:")
        print("烧录字幕...")
        r = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", merged,
                            "-vf", f"subtitles='{ass_ff}'",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-c:a", "copy", "-movflags", "+faststart", final])
        if r.returncode != 0:
            print("字幕烧录失败，输出无字幕版")
            shutil.copy(merged, final)

    print(f"\n成片：{final} ({os.path.getsize(final)/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
