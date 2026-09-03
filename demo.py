"""Btrans 公开 API 演示：基础翻译、缓存命中与异常处理。"""

from __future__ import annotations

from Btrans import Translator
from Btrans.exceptions import TranslationArgumentError, TranslationError

HELLO_EN = "Hello, world!"
HELLO_ZH = "你好，世界！"


def demo_basic_translation(translator: Translator) -> None:
    print("[1] 基础翻译 en -> zh")
    result = translator.translate(
        HELLO_EN,
        from_lang="en",
        to_lang="zh",
    )
    print(f"输入：{HELLO_EN}")
    print(f"输出：{result.text}")
    print(f"检测语言：{result.detected_language}")
    print(f"当前缓存条目数：{translator.get_cache_size()}")

    print("\n[2] 基础翻译 zh -> en")
    result = translator.translate(
        HELLO_ZH,
        from_lang="zh",
        to_lang="en",
    )
    print(f"输入：{HELLO_ZH}")
    print(f"输出：{result.text}")
    print(f"检测语言：{result.detected_language}")
    print(f"当前缓存条目数：{translator.get_cache_size()}")


def demo_cache_hit(translator: Translator) -> None:
    print("\n[3] 缓存命中：再次翻译与第 1 步相同的文本")
    result = translator.translate(
        HELLO_EN,
        from_lang="en",
        to_lang="zh",
    )
    print(f"再次输出：{result.text}")
    print(f"当前缓存条目数：{translator.get_cache_size()}")
    print("说明：第 3 步命中本地缓存，没有再次发起真实翻译请求。")


def demo_exception_handling(translator: Translator) -> None:
    print("\n[4] 异常处理：空文本应被拦截")
    try:
        translator.translate(
            "   ",
            from_lang="en",
            to_lang="zh",
        )
    except TranslationArgumentError as exc:
        print(f"已捕获 {type(exc).__name__}: {exc}")
    else:
        raise AssertionError("空文本没有抛出异常")

    print("\n[5] 异常处理：不支持的源语言应被拦截")
    try:
        translator.translate(
            HELLO_EN,
            from_lang="fr",
            to_lang="zh",
        )
    except TranslationArgumentError as exc:
        print(f"已捕获 {type(exc).__name__}: {exc}")
    else:
        raise AssertionError("非法语言没有抛出异常")


def main() -> int:
    print("Bing Translate 在线翻译演示\n")
    translator = Translator(enable_cache=True, cache_dir="./my_cache")
    translator.clear_cache()
    try:
        demo_basic_translation(translator)
        demo_cache_hit(translator)
        demo_exception_handling(translator)
    except TranslationError as exc:
        print(f"翻译失败：{exc}")
        return 1

    print(f"\n最终缓存条目数：{translator.get_cache_size()}")
    print("演示结束。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
