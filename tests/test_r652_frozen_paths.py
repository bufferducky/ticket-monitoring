# -*- coding: utf-8 -*-
"""r652：打包（PyInstaller）后，数据/登录态必须落在 exe 所在目录。

实测：冻结态 `__file__` 指向 `_internal/`，于是 `data/prices.db`、
`user_data/` 全被拼进程序内部目录——用户在安装目录下看不到自己的数据，
升级或重装一次就随包一起被清掉。源码态必须保持仓库根不变。
"""
import os
import sys
import importlib.util
import shutil

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import paths


@pytest.fixture
def bundled_webui(monkeypatch, tmp_path):
    """按真实打包布局加载整个 webui，覆盖模块初始化时的根目录选择。"""
    import main

    app = tmp_path / "TicketMonitor"
    internal = app / "_internal"
    internal.mkdir(parents=True)
    source = os.path.join(os.path.dirname(main.__file__), "webui.py")
    target = internal / "webui.py"
    shutil.copyfile(source, target)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app / "TicketMonitor"))
    monkeypatch.setattr(main, "_REPO_ROOT", str(app))
    name = "_bundled_webui_paths_test"
    spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    module._State.cfg = {}
    module._State.boot_cfg = {}
    return module, app


@pytest.mark.parametrize("session_dir", [None, "profiles", "absolute"])
def test_bundled_login_and_fetch_share_saved_session(bundled_webui, session_dir):
    """网页登录写入的凭据必须被同一配置下的采集器读到。"""
    import logging
    import main
    from core.login_slots import slot_crawler
    from crawlers.ctrip import CtripCrawler

    ui, app = bundled_webui
    if session_dir == "absolute":
        session_dir = str(app.parent / "custom-profiles")
    crawler_cfg = {"user_data_dir": session_dir} if session_dir else {}
    ui._State.boot_cfg = {"crawler": crawler_cfg}
    fetch_cfg = dict(crawler_cfg, user_data_dir=main._anchored(
        session_dir, "user_data"))
    logger = logging.getLogger("test-bundled-paths")
    login = slot_crawler("ctrip", ui._effective_crawler_config(), logger)
    fetch = CtripCrawler(fetch_cfg, logger)
    assert login.session_state_path == fetch.session_state_path
    login._write_session_state({"cookies": [{
        "name": "cticket", "value": "synthetic-test-ticket",
        "domain": ".ctrip.com", "path": "/", "expires": -1,
    }], "origins": []}, 1700000000)
    assert any(c["name"] == "cticket" for c in fetch.load_session_cookies())


def test_bundled_webui_storage_paths_use_executable_dir(bundled_webui):
    ui, app = bundled_webui
    assert ui._anchored(None, "data/prices.db") == str(app / "data/prices.db")
    assert ui._anchored(None, "logs/monitor.log") == str(app / "logs/monitor.log")


def test_source_mode_uses_repo_root(monkeypatch):
    """源码态：根目录 = core/ 的上一级（仓库根）。"""
    monkeypatch.delattr(sys, "frozen", raising=False)
    root = paths.app_root()
    assert os.path.isdir(os.path.join(root, "core")), root
    assert os.path.isdir(os.path.join(root, "crawlers")), root


def test_frozen_mode_uses_exe_dir(monkeypatch, tmp_path):
    """冻结态：根目录 = exe 所在目录，不是 _internal。"""
    exe = tmp_path / "TicketMonitor.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)
    assert paths.app_root() == str(tmp_path)


def test_relative_paths_anchor_to_exe_dir(monkeypatch, tmp_path):
    """`data/prices.db` 这类相对路径要拼到 exe 目录下。"""
    exe = tmp_path / "TicketMonitor.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)
    got = paths.resolve("data/prices.db").replace("\\", "/")
    want = (str(tmp_path) + "/data/prices.db").replace("\\", "/")
    assert got == want, "%s != %s" % (got, want)
    # 绝对路径原样（用平台真实的绝对路径，别写死 Windows 盘符——
    # `D:\...` 在 POSIX 上不是绝对路径，这条断言在 CI 上必红）
    abs_path = os.path.join(os.sep, "other", "a.db")
    assert paths.resolve(abs_path) == abs_path


def test_main_and_crawlers_use_app_root_when_frozen():
    """三处根解析都要接上 core.paths，否则只修一半仍会写错位置。"""
    import io
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ("main.py", "crawlers/base.py", "crawlers/app_base.py"):
        src = io.open(os.path.join(root, rel), encoding="utf-8",
                      newline="").read()
        assert "core.paths import app_root" in src, "%s 未接 app_root" % rel
        assert 'getattr(sys, "frozen", False)' in src, "%s 未判冻结态" % rel
