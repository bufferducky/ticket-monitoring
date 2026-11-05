"""调试文件必须落到程序目录，写入失败不能中断价格采集。"""
import logging

import pytest

from crawlers import base
from crawlers.ctrip import CtripCrawler
from crawlers.qunar import QunarCrawler


@pytest.mark.parametrize("crawler_cls", [QunarCrawler, CtripCrawler])
@pytest.mark.parametrize("debug_dir", [None, "", "  ", "captures"])
def test_debug_output_uses_app_root(crawler_cls, debug_dir, tmp_path, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()
    cwd = tmp_path / "unrelated-working-directory"
    cwd.mkdir()
    monkeypatch.setattr(base, "_REPO_ROOT", str(app))
    monkeypatch.chdir(cwd)
    crawler = crawler_cls({"debug": True, "debug_dir": debug_dir},
                          logging.getLogger("test-debug-output"))

    if crawler_cls is QunarCrawler:
        crawler._dump_raw_text("synthetic-response", "sample")
        filename = "qunar_raw_sample.txt"
    else:
        crawler._dump_xhr([{"url": "https://example.test/flight",
                            "text": "synthetic-response"}], "sample")
        filename = "sample.txt"

    target = app / ("captures" if debug_dir == "captures" else "debug") / filename
    assert "synthetic-response" in target.read_text()
    assert list(cwd.iterdir()) == []


@pytest.mark.parametrize("crawler_cls", [QunarCrawler, CtripCrawler])
def test_debug_output_failure_does_not_abort_fetch(crawler_cls, tmp_path):
    # 真实文件系统失败：目标的父路径已是文件，无法创建目录。
    parent = tmp_path / "not-a-directory"
    parent.write_text("existing-file")
    crawler = crawler_cls({"debug": True, "debug_dir": str(parent / "captures")},
                          logging.getLogger("test-debug-output"))
    if crawler_cls is QunarCrawler:
        crawler._dump_raw_text("synthetic-response", "sample")
    else:
        crawler._dump_xhr([{"url": "https://example.test/flight",
                            "text": "synthetic-response"}], "sample")
    assert parent.read_text() == "existing-file"


def test_absolute_debug_directory_is_respected(tmp_path):
    crawler = QunarCrawler({"debug": True, "debug_dir": str(tmp_path)},
                           logging.getLogger("test-debug-output"))
    crawler._dump_raw_text("synthetic-response", "sample")
    assert (tmp_path / "qunar_raw_sample.txt").read_text() == "synthetic-response"
