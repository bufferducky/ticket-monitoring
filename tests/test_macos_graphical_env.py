"""桌面登录不能把 macOS 缺少 X11/Wayland 变量误判成无图形环境。"""
import os
from types import SimpleNamespace

import pytest

import webui
from webui import _no_graphical_env as detect_no_gui


@pytest.mark.parametrize(
    ("platform", "display", "wayland", "expected"),
    [
        ("darwin", None, None, False),
        ("win32", None, None, False),
        ("linux", None, None, True),
        ("linux", ":0", None, False),
        ("linux", None, "wayland-0", False),
        ("linux", "", "", True),
    ],
)
def test_native_desktop_and_headless_linux(monkeypatch, platform, display,
                                          wayland, expected):
    # conftest 为其它登录用例替换了入口；保留导入时的真函数来验证平台检测。
    monkeypatch.setattr(webui, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(webui, "os", SimpleNamespace(
        name="nt" if platform == "win32" else "posix", environ=os.environ))
    for name, value in (("DISPLAY", display), ("WAYLAND_DISPLAY", wayland)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert detect_no_gui() is expected
