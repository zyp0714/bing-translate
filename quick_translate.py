"""命令行在线翻译工具。"""

from __future__ import annotations

import argparse
import sys

from Btrans import Translator
from Btrans.exceptions import TranslationArgumentError, TranslationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用 Bing 在线翻译任意文本"
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="要翻译的文本；不填写则进入交互模式",
    )
    parser.add_argument(
        "-f",
        "--from-lang",
        choices=("auto", "zh", "en"),
        default="auto",
        help="源语言，默认 auto",
    )
    parser.add_argument(
        "-t",
        "--to-lang",
        choices=("zh", "en"),
        default="en",
        help="目标语言，默认 en",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用本地缓存",
    )
    parser.add_argument(
        "--cache-dir",
        default="./my_cache",
        help="缓存目录，默认 ./my_cache",
    )
    return parser


def translate_once(
    translator: Translator,
    text: str,
    source: str,
    target: str,
) -> None:
    result = translator.translate(
        text,
        from_lang=source,
        to_lang=target,
    )
    print(result.text)
    if result.detected_language:
        print(f"[detected: {result.detected_language}]")


def run_interactive(translator: Translator, source: str, target: str) -> None:
    print("交互模式：输入一行文本按回车翻译，输入 exit 退出")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        if text.lower() in {"exit", "quit", "q"}:
            return
        try:
            translate_once(translator, text, source, target)
        except TranslationError as exc:
            print(f"translation failed: {exc}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    translator = Translator(
        enable_cache=not args.no_cache,
        cache_dir=args.cache_dir,
    )

    if args.text is None:
        run_interactive(
            translator,
            source=args.from_lang,
            target=args.to_lang,
        )
        return 0

    try:
        translate_once(
            translator,
            text=args.text,
            source=args.from_lang,
            target=args.to_lang,
        )
    except TranslationArgumentError as exc:
        print(f"invalid arguments: {exc}")
        return 2
    except TranslationError as exc:
        print(f"translation failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

