"""Bing Translate 统一异常继承树。"""

from __future__ import annotations


class TranslationError(Exception):
    """公开翻译 API 抛出的所有错误的公共基类。"""


class TranslationArgumentError(TranslationError):
    """调用参数非法时抛出，例如空文本或无效语言代码。"""


class ParamError(TranslationError):
    """获取或解析页面参数相关错误的基类。"""


class ParamExtractionError(ParamError):
    """Bing 首页未暴露预期字段时抛出。"""


class TranslationCacheError(TranslationError):
    """本地缓存读写错误的基类。"""


class TranslationClientError(TranslationError):
    """低层翻译 HTTP 请求相关错误的基类。"""


class InvalidParameterResponse(TranslationClientError):
    """服务器判定当前动态参数失效（HTTP 205/400）。"""


class TranslationRequestError(TranslationClientError):
    """HTTP 请求失败或返回了非预期状态码。"""


class ResponseParseError(TranslationClientError):
    """响应体无法解码，或无法解析为翻译 JSON。"""
