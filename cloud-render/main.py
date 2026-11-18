# -*- coding: utf-8 -*-
"""
漫剧二创 · 全自动云端渲染服务
- POST /api/upload?job=<id>   上传原片（逐集，≤50MB/集）
- POST /api/jobs              创建渲染任务（带方案 shots）
- GET  /api/job?id=<id>       查询任务状态/进度
- GET  /api/download/<id>/mp4 下载成片
- GET  /api/download/<id>/zip 下载剪映工程包（含素材）
- GET  /                      前端页面
渲染在后台线程执行：ffmpeg 整集连播拼接 + 烧录金句字幕 + 生成剪映工程。
"""
import os, sys, json, time, uuid, shutil, subprocess, threading, zipfile, traceback, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", 3000))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data")
JOBS = {}
JOB_LOCK = threading.Lock()
MAX_UPLOAD = 50 * 1024 * 1024
MAX_JOBS_KEEP = 20


def get_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


FFMPEG = get_ffmpeg()


def run(cmd, timeout=3600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ffprobe_duration(path):
    r = run([FFMPEG, "-i", path], timeout=60)
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mi * 60 + s
    return 0.0


def ts(x):
    h = int(x // 3600); mi = int((x % 3600) // 60); s = x % 60
    return f"{h:d}:{mi:02d}:{s:05.2f}"


def write_ass(path, shots, width, height, gold_sec):
    ass = ["[Script Info]", "ScriptType: v4.00+",
           f"PlayResX: {width}", f"PlayResY: {height}",
           "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: Gold,Microsoft YaHei,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,4,1,2,60,60,300,1", "",
           "[Events]",
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    cursor = 0.0
    for sh in shots:
        dur = float(sh.get("duration", 0))
        sub = sh.get("subtitle", "")
        if sub:
            gs = cursor + 0.5
            ge = min(cursor + dur, gs + gold_sec)
            if ge > gs:
                g = str(sub).replace("{", "(").replace("}", ")").replace("\n", " ")
                ass.append(f"Dialogue: 0,{ts(gs)},{ts(ge)},Gold,,0,0,0,,{g}")
        cursor += dur
    open(path, "w", encoding="utf-8").write("\n".join(ass))


def build_jianying(job_dir, shots, fps, width, height, gold_sec):
    """生成剪映草稿工程（pyJianYingDraft）。"""
    try:
        import pyJianYingDraft as d
        from pyJianYingDraft import (VideoMaterial, VideoSegment, TextSegment,
            Timerange, TrackType, TrackSpec, TextStyle, TextBorder, ClipSettings, SEC)
    except Exception as e:
        return None, "pyJianYingDraft 不可用: " + str(e)[:100]
    draft_dir = os.path.join(job_dir, "剪映工程", "草稿")
    os.makedirs(draft_dir, exist_ok=True)
    try:
        folder = d.DraftFolder(draft_dir)
        script = folder.create_draft("云端成片", width, height, fps,
                                     maintrack_adsorb=True, allow_replace=True)
        vt = script.append_track(TrackSpec(TrackType.video, "主视频"))
        tt = script.append_track(TrackSpec(TrackType.text, "金句字幕"))
        style = TextStyle(size=9.0, bold=True, color=(1, 1, 1), align=1)
        border = TextBorder(color=(0, 0, 0), alpha=1.0, width=50.0)
        clip = ClipSettings(transform_y=-0.78)
        vdur = {}
        cursor = 0.0
        for idx, sh in enumerate(shots):
            src = os.path.join("素材", os.path.basename(sh["file"]))
            src_abs = sh.get("_local", src)
            key = os.path.basename(src)
            if key not in vdur:
                vdur[key] = VideoMaterial(src_abs).duration
            ss = int(round(float(sh.get("src_sec", 0)) * SEC))
            sd = int(round(float(sh["duration"]) * SEC))
            tls = int(round(cursor * SEC))
            if ss + sd > vdur[key]:
                sd = vdur[key] - ss
            if sd <= 0:
                cursor += float(sh["duration"]); continue
            script.add_segment(VideoSegment(src, Timerange(tls, sd),
                               source_timerange=Timerange(ss, sd)), vt)
            sub = sh.get("subtitle", "")
            gd = int(min(gold_sec, float(sh["duration"]) - 0.5) * SEC)
            if sub and gd > 0:
                script.add_segment(TextSegment(sub, Timerange(tls + int(0.5*SEC), gd),
                                   style=style, border=border, clip_settings=clip), tt)
            cursor += float(sh["duration"])
        script.save()
        return draft_dir, None
    except Exception as e:
        return None, str(e)[:200]


def render_job(job_id):
    job = JOBS[job_id]
    job_dir = job["dir"]
    try:
        cfg = job["cfg"]
        shots = job["shots"]
        if not shots:
            raise RuntimeError("没有剪辑方案")
        fps = int(cfg.get("fps", 30))
        width = int(cfg.get("width", 1080))
        height = int(cfg.get("height", 1920))
        gold_sec = float(cfg.get("gold_sec", 5))
        src_dir = os.path.join(job_dir, "src")
        for sh in shots:
            sh["_local"] = os.path.join(src_dir, sh["file"])

        job["status"] = "rendering"; job["progress"] = 5; job["stage"] = "校验原片"
        cursor = 0.0
        for sh in shots:
            p = sh["_local"]
            if not os.path.exists(p):
                raise RuntimeError("缺少原片: " + sh["file"])
            if sh.get("full_episode") or not sh.get("duration"):
                sh["duration"] = round(ffprobe_duration(p))
            cursor += float(sh["duration"])
        job["total_sec"] = round(cursor)

        seg_dir = os.path.join(job_dir, "segments")
        os.makedirs(seg_dir, exist_ok=True)
        segs = []
        n = len(shots)
        for i, sh in enumerate(shots):
            job["stage"] = f"截取原片 {i+1}/{n}"
            job["progress"] = 5 + int((i / n) * 55)
            out = os.path.join(seg_dir, f"{i:03d}.mp4")
            ss = float(sh.get("src_sec", 0))
            cmd = [FFMPEG, "-y", "-v", "error", "-ss", str(ss), "-i", sh["_local"],
                   "-t", str(sh["duration"]),
                   "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                   "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                   "-movflags", "+faststart", out]
            r = run(cmd)
            if r.returncode != 0 or not os.path.exists(out):
                raise RuntimeError(f"片段 {i+1} 截取失败: {r.stderr[-200:]}")
            segs.append(out)

        job["stage"] = "拼接成片"; job["progress"] = 62
        lf = os.path.join(job_dir, "concat.txt")
        open(lf, "w", encoding="utf-8").write(
            "".join("file '" + p.replace("\\", "/") + "'\n" for p in segs))
        merged = os.path.join(job_dir, "_merged.mp4")
        r = run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0",
                 "-i", lf, "-c", "copy", merged])
        if r.returncode != 0:
            raise RuntimeError("拼接失败: " + r.stderr[-200:])

        job["stage"] = "烧录金句字幕"; job["progress"] = 72
        final = os.path.join(job_dir, "成片.mp4")
        ass = os.path.join(job_dir, "金句字幕.ass")
        write_ass(ass, shots, width, height, gold_sec)
        ass_ff = ass.replace("\\", "/").replace(":", "\\:")
        r = run([FFMPEG, "-y", "-v", "error", "-i", merged,
                 "-vf", f"subtitles='{ass_ff}'",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-c:a", "copy", "-movflags", "+faststart", final], timeout=3600)
        if r.returncode != 0 or not os.path.exists(final):
            shutil.copy(merged, final)
            job["warn"] = "字幕烧录失败，已输出无字幕版"

        job["stage"] = "生成剪映工程包"; job["progress"] = 88
        draft_dir, derr = build_jianying(job_dir, shots, fps, width, height, gold_sec)
        zip_path = os.path.join(job_dir, "剪映工程包.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if draft_dir and os.path.isdir(draft_dir):
                for root, _, files in os.walk(draft_dir):
                    for fn in files:
                        fp = os.path.join(root, fn)
                        zf.write(fp, os.path.join("剪映草稿", os.path.relpath(fp, draft_dir)))
            else:
                zf.writestr("说明.txt", "剪映工程生成失败：" + str(derr))
            for sh in shots:
                zf.write(sh["_local"], os.path.join("素材", os.path.basename(sh["file"])))
            zf.writestr("使用说明.txt",
                "1) 解压；2) 把『剪映草稿』文件夹整个复制到剪映草稿目录；"
                "3) 打开剪映进入草稿，若素材离线，在素材管理里点『重新链接』指向解压出的『素材』文件夹；"
                "4) 加 BGM 后导出。")

        shutil.rmtree(seg_dir, ignore_errors=True)
        for f in (merged, lf):
            try: os.remove(f)
            except: pass
        job["status"] = "done"; job["progress"] = 100; job["stage"] = "完成"
        job["size_mb"] = round(os.path.getsize(final) / 1024 / 1024, 1)
    except Exception as e:
        job["status"] = "error"; job["error"] = str(e)[:300]
        job["trace"] = traceback.format_exc()[-600:]
        print("JOB ERROR", job_id, job.get("trace"), flush=True)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, name, ctype="application/octet-stream", inline=False):
        if not os.path.exists(path):
            self._json({"error": "文件不存在"}, 404); return
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        disp = "inline" if inline else "attachment"
        # HTTP 头只能 latin-1；非 ASCII 文件名走 RFC 5987 编码，回退 ASCII 名
        try:
            name.encode("latin-1")
            disp_val = f'{disp}; filename="{name}"'
        except UnicodeEncodeError:
            from urllib.parse import quote as _q
            ascii_name = "download" + os.path.splitext(name)[1]
            disp_val = f"{disp}; filename=\"{ascii_name}\"; filename*=UTF-8''{_q(name)}"
        self.send_header("Content-Disposition", disp_val)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(path, "rb") as f:
            while True:
                b = f.read(1024 * 1024)
                if not b: break
                try: self.wfile.write(b)
                except: break

    def do_GET(self):
        u = urlparse(self.path); path = u.path; qs = parse_qs(u.query)
        if path == "/api/job":
            job = JOBS.get(qs.get("id", [""])[0])
            if not job:
                self._json({"error": "任务不存在"}, 404); return
            keys = ("id","status","progress","stage","total_sec","size_mb","error","warn")
            self._json({k: job[k] for k in keys if k in job}); return
        if path.startswith("/api/download/"):
            parts = path.split("/")
            if len(parts) >= 5:
                job = JOBS.get(parts[3])
                if not job:
                    self._json({"error": "任务不存在"}, 404); return
                d = job["dir"]; kind = parts[4]
                if kind == "mp4":
                    self._file(os.path.join(d, "成片.mp4"), "成片.mp4", "video/mp4"); return
                if kind == "zip":
                    self._file(os.path.join(d, "剪映工程包.zip"), "剪映工程包.zip", "application/zip"); return
            self._json({"error": "参数错误"}, 400); return
        if path in ("/", "/index.html"):
            page = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
            self._file(page, "index.html", "text/html; charset=utf-8", inline=True); return
        if path == "/sdk.js":
            sdk = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sdk.js")
            self._file(sdk, "sdk.js", "application/javascript; charset=utf-8", inline=True); return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path); path = u.path
        if path == "/api/upload":
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_UPLOAD + 1024 * 1024:
                self._json({"error": "单集超过 50MB，请先压缩"}, 413); return
            ctype = self.headers.get("Content-Type", "")
            boundary = ctype.split("boundary=", 1)[1].strip().strip('"') if "boundary=" in ctype else ""
            remaining = length; data = b""
            while remaining > 0:
                b = self.rfile.read(min(1024 * 1024, remaining))
                if not b: break
                data += b; remaining -= len(b)
            m = re.search(rb'filename="([^"]+)"', data[:4096])
            fname = os.path.basename(m.group(1).decode("utf-8", "replace")) if m else "upload.mp4"
            marker = b"\r\n\r\n"; si = data.find(marker)
            ei = data.rfind(b"\r\n--" + boundary.encode()) if boundary else -1
            content = data[si+4:ei] if si >= 0 and ei > si else data
            ext = os.path.splitext(fname)[1].lower()
            if ext not in (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"):
                ext = ".mp4"
            jid = parse_qs(u.query).get("job", [None])[0] or ("tmp_" + uuid.uuid4().hex[:12])
            src_dir = os.path.join(ROOT, jid, "src"); os.makedirs(src_dir, exist_ok=True)
            safe = re.sub(r'[^0-9A-Za-z一-龥._-]', '_', os.path.splitext(fname)[0]) + ext
            with open(os.path.join(src_dir, safe), "wb") as f:
                f.write(content)
            self._json({"ok": True, "file": safe, "job": jid, "bytes": len(content)}); return

        if path == "/api/jobs":
            length = int(self.headers.get("Content-Length", 0)); body = b""
            while length > 0:
                b = self.rfile.read(min(1024*1024, length))
                if not b: break
                body += b; length -= len(b)
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception as e:
                self._json({"error": "无效 JSON: " + str(e)}, 400); return
            jid = payload.get("job") or ("job_" + uuid.uuid4().hex[:12])
            # 若上传时用了临时 job id，复用其 src
            tmp_src = os.path.join(ROOT, jid, "src")
            job_dir = os.path.join(ROOT, jid)
            os.makedirs(job_dir, exist_ok=True)
            job = {"id": jid, "dir": job_dir, "status": "queued", "progress": 0,
                   "stage": "排队中", "shots": payload.get("shots", []),
                   "cfg": payload.get("config", {}), "created": time.time()}
            with JOB_LOCK:
                JOBS[jid] = job
                old = sorted(JOBS.values(), key=lambda j: j["created"])[:-MAX_JOBS_KEEP]
                for o in old:
                    shutil.rmtree(o["dir"], ignore_errors=True); JOBS.pop(o["id"], None)
            threading.Thread(target=render_job, args=(jid,), daemon=True).start()
            self._json({"ok": True, "id": jid}); return

        self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    os.makedirs(ROOT, exist_ok=True)
    print("cloud render service on", PORT, flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
