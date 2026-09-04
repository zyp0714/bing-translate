"""支持通过 `python -m Btrans` 调用命令行入口。"""

from __future__ import annotations

from Btrans.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
