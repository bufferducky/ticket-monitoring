"""从干净提交树的 PyInstaller 产物生成不含运行数据的 Apple Silicon 发布包。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
NAME = "ticket-monitoring-macos-arm64-channel-fix"
NOTES = "docs/release-notes-v1.5.307-macos-channel-fix.md"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build-dir", type=Path, default=ROOT / "dist/TicketMonitor")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "dist_package")
    ap.add_argument("--validation", required=True, help="本次实际执行的测试摘要")
    args = ap.parse_args()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT, text=True)
    if status.strip():
        raise SystemExit("需要干净提交树；请先提交源码与说明，再构建发布包")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     text=True).strip()
    version = re.search(r'__version__ = "([^"]+)"',
                        (ROOT / "main.py").read_text()).group(1)
    executable = args.build_dir / "TicketMonitor"
    actual = subprocess.check_output([str(executable.resolve()), "--version"],
                                     text=True).strip()
    if actual != version:
        raise SystemExit(f"版本不符：源码 {version} / 可执行 {actual}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    folder = args.output_dir / NAME
    if folder.exists():
        raise SystemExit(f"输出目录已存在，请选择新目录：{folder}")
    shutil.copytree(args.build_dir, folder)
    shutil.copy2(ROOT / "tools/macos-service.zsh", folder / ".ticket-monitor-service.zsh")
    for title, action in (("启动", "start"), ("停止", "stop"),
                          ("重启", "restart"), ("查看状态", "status")):
        p = folder / f"{title}.command"
        p.write_text('#!/bin/zsh\nexec /bin/zsh "${0:A:h}/.ticket-monitor-service.zsh" '
                     + action + '\n')
        p.chmod(0o755)
    test = folder / "启动测试.command"
    test.write_text('#!/bin/zsh\ncd -- "${0:A:h}" || exit 1\n'
                    'exec ./TicketMonitor --config macos-test-config.yaml "$@"\n')
    test.chmod(0o755)
    (folder / "macos-test-config.yaml").write_text(
        "users: []\nweb:\n  host: 127.0.0.1\n  port: 8766\nschedule:\n"
        "  interval_minutes: 30\n  jitter_minutes: 5\n  run_on_start: false\n"
        "crawler:\n  headless: true\n  debug: true\noutput:\n"
        "  db_path: test-data/prices.db\n  log_path: test-logs/monitor.log\n")
    shutil.copy2(ROOT / NOTES, folder / "更新与使用说明.md")
    (folder / "启停说明.txt").write_text(
        "双击「启动.command」后台运行，终端和浏览器均可关闭。\n"
        "操作界面：http://127.0.0.1:8765\n"
        "使用「停止.command」「重启.command」「查看状态.command」管理服务。\n"
        "默认不设置登录 Mac 时自动启动。首次运行会下载 Chromium。\n"
        "「启动测试.command」使用端口 8766，需保留终端，按 Control+C 退出。\n"
        "同一目录只能运行一个实例；升级步骤见「更新与使用说明.md」。\n")
    sources = ["main.py", "webui.py", "crawlers/base.py", "crawlers/qunar.py",
               "crawlers/ctrip.py", "crawlers/tuniu.py", "core/health.py",
               "TicketMonitor.spec", "tools/macos-service.zsh", "tools/package_macos.py"]
    info = {"build": "macos-arm64-channel-fix-20261105", "version": version,
            "source_commit": commit, "architecture": "arm64",
            "service_mode": "manual-background", "validation": args.validation,
            "source_sha256": {p: sha256(ROOT / p) for p in sources},
            "binary_sha256": sha256(folder / "TicketMonitor")}
    (folder / "BUILD_INFO.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
    archive = Path(shutil.make_archive(str(args.output_dir / NAME), "zip", folder))
    digest = sha256(archive)
    archive.with_suffix(".zip.sha256").write_text(digest + "  " + archive.name + "\n")
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        forbidden = {"config.yaml", "data", "logs", "user_data", "debug", "test-data",
                     "test-logs", ".service", ".backups", ".env", ".git"}
        for name in z.namelist():
            parts = Path(name).parts
            assert not any(p in forbidden for p in parts), name
            assert not any(p.startswith(".TicketMonitor") or p == "session-state.json"
                           or p == "token.json" for p in parts), name
        assert sha256(executable) == hashlib.sha256(z.read("TicketMonitor")).hexdigest()
        assert (z.getinfo("启动.command").external_attr >> 16) & 0o111
    print(archive.resolve())
    print("source_commit:", commit)
    print("SHA256:", digest)


if __name__ == "__main__":
    main()
