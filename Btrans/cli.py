"""Bing 在线翻译命令行入口。"""

from __future__ import annotations

import argparse
import re
import sys

from Btrans import Translator
from Btrans.exceptions import TranslationArgumentError, TranslationError

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


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
        choices=("auto", "zh", "en"),
        default="auto",
        help="目标语言，默认自动选择与输入相反的语言",
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
    target = effective_target(text, source, target)
    result = translator.translate(
        text,
        from_lang=source,
        to_lang=target,
    )
    print(result.text)
    if result.detected_language:
        print(f"[detected: {result.detected_language}]")


def effective_target(text: str, source: str, target: str) -> str:
    """把 auto 目标解析成与输入语言相反的具体语言。"""

    if target != "auto":
        return target
    if source == "zh":
        return "en"
    if source == "en":
        return "zh"
    return "en" if _CJK_RE.search(text) else "zh"


def run_interactive(translator: Translator, source: str, target: str) -> None:
    print(
        "交互模式：直接输入文本翻译；"
        "输入 --to zh / --to en / --to auto 切换目标语言；"
        "输入 --from auto / zh / en 切换源语言；输入 exit 退出"
    )
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
        if text.startswith("--to"):
            parts = text.split()
            if len(parts) == 2 and parts[1] in {"zh", "en", "auto"}:
                target = parts[1]
                print(f"目标语言已切换为 {target}")
            else:
                print("用法：--to zh / --to en / --to auto")
            continue
        if text.startswith("--from"):
            parts = text.split()
            if len(parts) == 2 and parts[1] in {"auto", "zh", "en"}:
                source = parts[1]
                print(f"源语言已切换为 {source}")
            else:
                print("用法：--from auto / --from zh / --from en")
            continue
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
