#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 SKILL.md frontmatter 并重新打包 manju-erchuang Skill。"""
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "manju-erchuang")
DST = os.path.join(ROOT, "..", "发布包", "manju-erchuang.zip")


def check_frontmatter():
    path = os.path.join(SRC, "SKILL.md")
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if lines[0].strip() != "---":
        raise SystemExit("SKILL.md 缺少 frontmatter 起始 ---")
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    block = "\n".join(lines[1:end])
    try:
        import yaml
        data = yaml.safe_load(block)
        print("YAML 解析成功，字段：", ", ".join(data.keys()))
    except ImportError:
        print("未安装 PyYAML，执行基础语法检查：")
        for idx, line in enumerate(lines[1:end], start=2):
            key, sep, val = line.partition(":")
            if not sep or not key.strip():
                raise SystemExit(f"第 {idx} 行不是合法 key: value：{line[:80]}")
            val = val.strip()
            if val and not val[0] in ('"', "'") and (": " in val or " #" in val):
                raise SystemExit(f"第 {idx} 行含未引号包裹的冒号/井号：{line[:80]}")
        print("基础检查通过")


def pack():
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for dirpath, dirnames, filenames in os.walk(SRC):
            dirnames.sort()
            filenames.sort()
            for name in filenames:
                full = os.path.join(dirpath, name)
                arc = os.path.join(
                    "manju-erchuang", os.path.relpath(full, SRC)
                ).replace(os.sep, "/")
                zf.write(full, arc)
    print("打包完成：", DST, os.path.getsize(DST), "bytes")
    with zipfile.ZipFile(DST) as zf:
        for name in zf.namelist():
            print(" -", name)
        skill = zf.read("manju-erchuang/SKILL.md").decode("utf-8").splitlines()
        print("zip 内 SKILL.md 前 11 行：")
        for line in skill[:11]:
            print("   ", line)


if __name__ == "__main__":
    check_frontmatter()
    pack()
