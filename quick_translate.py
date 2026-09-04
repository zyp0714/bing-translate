"""命令行在线翻译工具（兼容独立脚本调用）。"""

from __future__ import annotations

import sys

from Btrans.cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
