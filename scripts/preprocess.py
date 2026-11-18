# -*- coding: utf-8 -*-
"""
步骤1 · 视频预处理：抽帧 + 导出音频 + 智能粗筛候选点。

用法：
  python preprocess.py <视频文件或文件夹> [采样间隔秒数] [输出目录]

示例：
  python preprocess.py "待分析视频/某剧/第1集.mp4" 2
  python preprocess.py "待分析视频/某剧" 3 "分析输出/某剧"

依赖：ffmpeg / ffprobe 在 PATH 中（可用 --ffmpeg 参数或环境变量 FFMPEG 指定）。

输出（默认在脚本同级 分析输出/ 下）：
  <剧集名>/frames/   关键帧截图（文件序号即时间码，见 info.json 索引）
  <剧集名>/audio.aac 音频（供语音转写）
  <剧集名>/info.json 元信息 + 时间码索引 + 候选点
  _候选点汇总.csv    所有集的候选点汇总（文件夹模式时生成）

说明：短剧镜头密，粗筛候选点仅作定位参考；核心价值在于随后对
audio.aac 做全量语音转写，用台词定位情绪爆点。
"""
import sys, os, json, subprocess, csv, re, argparse

VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts")


def make_runner(ffmpeg, ffprobe):
    def run(cmd):
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    return run, ffmpeg, ffprobe


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


class Preprocessor:
    def __init__(self, ffmpeg, ffprobe, out_root):
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.out_root = out_root

    def run(self, cmd):
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    def probe(self, path):
        r = self.run([self.ffprobe, "-v", "error", "-show_entries",
                      "format=duration:stream=codec_type,width,height,r_frame_rate",
                      "-of", "json", path])
        try:
            return json.loads(r.stdout)
        except Exception:
            return {}

    def process(self, video, interval, group=""):
        name = os.path.splitext(os.path.basename(video))[0]
        out = os.path.join(self.out_root, group, name) if group else os.path.join(self.out_root, name)
        frames = os.path.join(out, "frames")
        os.makedirs(frames, exist_ok=True)

        info = self.probe(video)
        duration = float(info.get("format", {}).get("duration", 0))
        vs = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
        w, h = vs.get("width"), vs.get("height")
        print(f"\n=== {name} | {duration:.0f}s | {w}x{h} ===")

        # 抽帧：fps 滤镜按间隔取帧
        pattern = os.path.join(frames, "f_%05d.jpg")
        self.run([self.ffmpeg, "-y", "-i", video, "-vf",
                  f"fps={1.0/interval:.6f},scale=480:-2", "-q:v", "4", pattern])
        frame_files = sorted(f for f in os.listdir(frames) if f.endswith(".jpg"))

        # 导出音频
        audio = os.path.join(out, "audio.aac")
        r = self.run([self.ffmpeg, "-y", "-i", video, "-vn", "-acodec", "copy", audio])
        if r.returncode != 0 or not os.path.exists(audio):
            self.run([self.ffmpeg, "-y", "-i", video, "-vn", "-acodec", "aac",
                      "-b:a", "96k", audio])

        # 时间码索引
        index = []
        for i, fn in enumerate(frame_files):
            t = i * interval
            mm, ss = divmod(int(t), 60)
            index.append({"frame": fn, "second": round(t, 2),
                          "timecode": f"{mm:02d}:{ss:02d}"})

        with open(os.path.join(out, "info.json"), "w", encoding="utf-8") as f:
            json.dump({"video": os.path.basename(video), "duration": duration,
                       "width": w, "height": h, "interval": interval,
                       "frame_count": len(frame_files), "index": index},
                      f, ensure_ascii=False, indent=2)

        print(f"  关键帧 {len(frame_files)} 张 | 音频 {'OK' if os.path.exists(audio) else '失败'}")
        return name, out


def main():
    ap = argparse.ArgumentParser(description="漫剧二创 · 视频预处理")
    ap.add_argument("input", help="视频文件或文件夹")
    ap.add_argument("interval", nargs="?", type=float, default=2.0, help="采样间隔秒数，默认2")
    ap.add_argument("out_root", nargs="?", help="输出根目录，默认脚本同级/分析输出")
    ap.add_argument("--ffmpeg", default=os.environ.get("FFMPEG", "ffmpeg"))
    ap.add_argument("--ffprobe", default=os.environ.get("FFPROBE", "ffprobe"))
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    out_root = args.out_root or os.path.join(os.path.dirname(base), "分析输出")
    pre = Preprocessor(args.ffmpeg, args.ffprobe, out_root)

    if os.path.isfile(args.input):
        pre.process(args.input, args.interval)
        print("\n下一步：把 audio.aac 交给语音转写，逐帧看 frames/ 按五维模型打分。")
        return

    if not os.path.isdir(args.input):
        print("找不到:", args.input); sys.exit(1)

    items = []
    for root, dirs, files in os.walk(args.input):
        for f in files:
            if f.lower().endswith(VIDEO_EXT):
                rel = os.path.relpath(root, args.input)
                group = "" if rel == "." else os.path.basename(root)
                items.append((os.path.join(root, f), group, f))
    if not items:
        print("文件夹里没有视频。"); sys.exit(1)
    items.sort(key=lambda x: (x[1], natural_key(os.path.splitext(x[2])[0])))

    rows = []
    for video, group, fname in items:
        name, out = pre.process(video, args.interval, group)
        idx = json.load(open(os.path.join(out, "info.json"), encoding="utf-8"))["index"]
        for e in idx[::5]:  # 每 5 帧记一条，供人工快速扫
            rows.append([f"{group}/{name}" if group else name, e["timecode"], e["second"]])

    os.makedirs(out_root, exist_ok=True)
    csv_path = os.path.join(out_root, "_时间码索引.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["剧集", "时间点", "秒数"]); w.writerows(rows)
    print(f"\n全部完成：{len(items)} 集。索引表：{csv_path}")
    print("下一步：全量语音转写定位台词爆点，再按五维模型生成爆点清单。")


if __name__ == "__main__":
    main()
