#!/usr/bin/env python3
"""CBM 调用诊断脚本（排查 Windows 上 ``repo_path is required`` 报错）。

用法（在目标仓库根目录或任意目录运行）::

    python scripts/diagnose_cbm.py D:/source/NGCRM/crm/jbusiness

会逐个测试 CBM 的 4 种参数传递形式（flag / args-file / raw-json 位置参数 /
stdin），打印每种形式的实际命令和 CBM 响应。哪种形式能让 ``index_repository``
成功，就说明问题出在 RepoAgent 当前用的那种形式（``--args-file``）上。

不需要 OPENAI_API_KEY，也不需要安装 repoagent，只要有 codebase-memory-mcp。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list[str], stdin_data: str | None = None) -> tuple[int, str, str]:
    """运行命令，返回 (returncode, stdout, stderr)。"""
    proc = subprocess.run(
        cmd,
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def show(label: str, cmd: list[str], rc: int, out: str, err: str) -> None:
    print(f"\n{'=' * 70}\n{label}")
    print(f"  command: {' '.join(cmd)}")
    if err.strip():
        # 截断冗长的 mem.init 日志
        err_lines = [l for l in err.strip().splitlines() if "mem.init" not in l]
        if err_lines:
            print(f"  stderr : {err_lines[-1][:200]}")
    print(f"  exit   : {rc}")
    # 只打印结构化结果，截断
    body = out.strip()
    print(f"  stdout : {body[:400]}{'...' if len(body) > 400 else ''}")
    ok = '"isError":false' in body or '"status":"indexed"' in body
    print(f"  -> {'OK' if ok else 'FAILED'}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    repo = str(Path(sys.argv[1]).resolve())
    print(f"repo path: {repo}")
    print(f"exists   : {Path(repo).exists()}")

    # 检查 binary
    import shutil

    binary = shutil.which("codebase-memory-mcp")
    print(f"binary   : {binary}")
    if not binary:
        print("ERROR: codebase-memory-mcp not found in PATH")
        sys.exit(1)

    # CBM 版本
    rc, out, _ = run([binary, "--version"])
    print(f"version  : {out.strip()}")

    payload = {"repo_path": repo, "mode": "fast"}

    # 先清理可能存在的旧索引（避免误判）
    run([binary, "cli", "delete_project", "--project", repo, "--json"])

    # --- 形式 1: 逐个 flag（连字符规范形式）---
    cmd1 = [
        binary, "cli", "index_repository", "--json",
        "--repo-path", repo, "--mode", "fast",
    ]
    rc, out, err = run(cmd1)
    show("FORM 1: per-flag (hyphenated)", cmd1, rc, out, err)

    run([binary, "cli", "delete_project", "--project", repo, "--json"])

    # --- 形式 2: --args-file（RepoAgent 当前用的形式）---
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="cbm_diag_", delete=False
    ) as f:
        json.dump(payload, f)
        f.flush()
        args_path = f.name
    cmd2 = [binary, "cli", "index_repository", "--args-file", args_path, "--json"]
    rc, out, err = run(cmd2)
    show("FORM 2: --args-file (current RepoAgent)", cmd2, rc, out, err)
    try:
        os.unlink(args_path)
    except OSError:
        pass

    run([binary, "cli", "delete_project", "--project", repo, "--json"])

    # --- 形式 3: raw-json 位置参数 ---
    cmd3 = [binary, "cli", "index_repository", json.dumps(payload), "--json"]
    rc, out, err = run(cmd3)
    show("FORM 3: positional raw-json", cmd3, rc, out, err)

    run([binary, "cli", "delete_project", "--project", repo, "--json"])

    # --- 形式 4: stdin pipe ---
    cmd4 = [binary, "cli", "index_repository", "--json"]
    rc, out, err = run(cmd4, stdin_data=json.dumps(payload))
    show("FORM 4: stdin pipe", cmd4, rc, out, err)

    print(f"\n{'=' * 70}\n诊断完成。请把上面的全部输出贴给我。")


if __name__ == "__main__":
    main()
