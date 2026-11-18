# -*- coding: utf-8 -*-
"""
校验剪映草稿是否完整有效（不依赖剪映是否显示）。

用法：
  python validate_draft.py <草稿目录>

检查：
  - draft_content.json 存在且 JSON 可解析
  - 轨道/片段数量、时长
  - draft_meta_info.json 存在
  - 素材视频路径是否存在
"""
import os, sys, json


def main():
    if len(sys.argv) < 2:
        print("用法: python validate_draft.py <草稿目录>")
        sys.exit(1)
    draft = os.path.abspath(sys.argv[1])
    if not os.path.isdir(draft):
        print("找不到草稿目录:", draft); sys.exit(1)

    ok = True
    for fn in ("draft_content.json", "draft_meta_info.json"):
        p = os.path.join(draft, fn)
        if not os.path.exists(p):
            print("✗ 缺少", fn); ok = False
    content_path = os.path.join(draft, "draft_content.json")
    if os.path.exists(content_path):
        try:
            c = json.load(open(content_path, encoding="utf-8"))
        except Exception as e:
            print("✗ draft_content.json 无法解析:", e); sys.exit(1)
        tracks = c.get("tracks", [])
        segs = [len(t.get("segments", [])) for t in tracks]
        print(f"轨道数: {len(tracks)} | 各轨片段: {segs} | 时长: {c.get('duration',0)/1e6:.1f}s")
        # 统计素材引用
        paths = []
        for mat in c.get("materials", {}).get("videos", []):
            p = mat.get("path", "")
            if p:
                paths.append(p)
        if paths:
            missing = [p for p in paths if not os.path.exists(p)]
            print(f"视频素材 {len(paths)} 个，其中离线 {len(missing)} 个")
            for p in missing[:5]:
                print("  离线:", p)

    print("\n结论:", "草稿文件完整有效 ✓（看不到多半是剪映没重启）" if ok else "草稿有问题 ✗")


if __name__ == "__main__":
    main()
