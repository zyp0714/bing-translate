# bing-translate

用 Python 逆向实现微软 Bing 在线翻译（<https://cn.bing.com/translator>）的高可用翻译模块。项目动态提取页面鉴权参数，不硬编码任何 `IG`、`token`、`key`，并提供本地缓存、TTL、统计清理、异常继承树、CLI、demo 与单元测试。

## 功能

- 支持 `zh`、`en`、`auto` 三种源语言，以及 `zh`、`en` 目标语言
- 模拟真实浏览器请求头、Cookie 会话与 `br` / `gzip` / `deflate` 压缩响应处理
- 自动抓取并缓存 Bing 页面动态参数，参数失效后自动重试刷新
- 磁盘缓存 + TTL，默认 24 小时；提供清理、统计与禁用开关
- 完整异常继承树，缓存损坏或请求失败时可自动降级/重试
- 提供 `bing-translate` 命令、`quick_translate.py`、`demo.py` 与可安装的公开 API

## 快速开始

需要 Python >= 3.10，推荐使用 [uv](https://docs.astral.sh/uv/)。

### 1. 获取项目

```powershell
git clone https://github.com/zyp0714/bing-translate.git
cd bing-translate
```

### 2. 安装依赖

```powershell
uv sync
```

该命令会自动创建 `.venv`，安装 `requests`、`brotli` 及传递依赖，并以可编辑方式安装本项目。

### 3. 验证安装

Windows PowerShell 先设置中文输出编码：

```powershell
$env:PYTHONIOENCODING="utf-8"
```

然后验证导入：

```powershell
uv run python -c "from Btrans import Translator; print(Translator)"
```

能看到 `Translator` 即安装成功。

## 运行 demo

```powershell
uv run python demo.py
```

demo 会自动演示：中英互译、`auto` 自动识别、特殊字符、缓存命中与异常处理。真实翻译需要能访问 `cn.bing.com`，运行时会重建本地 `my_cache`。

## 命令行翻译

单条翻译：

```powershell
uv run python quick_translate.py "Hello, world!"
```

指定语言方向：

```powershell
uv run python quick_translate.py "你好，世界！" --to en
uv run python quick_translate.py "Bonjour" --from auto --to zh
```

交互模式：

```powershell
uv run python quick_translate.py
```

交互模式中直接输入文本翻译，可用 `--to zh / en / auto` 与 `--from auto / zh / en` 切换方向，输入 `exit` 退出。

项目安装后也可以直接使用生成的命令：

```powershell
uv run bing-translate "Hello, world!"
```

## Python API

```python
from Btrans import Translator

translator = Translator(enable_cache=True, cache_dir="./my_cache")

result = translator.translate(
    "Hello, world!",
    from_lang="en",
    to_lang="zh",
)

print(result.text)
print(result.detected_language)
```

支持的语言参数：

```text
from_lang: "auto" | "zh" | "en"
to_lang:   "zh" | "en"
```

## 运行测试

测试全部使用 mock，不依赖真实网络：

```powershell
uv run python -m unittest discover -s tests -v
```

## 逆向思路

1. 打开 [Bing 翻译网页端](https://cn.bing.com/translator)，按 F12 进入开发者工具，输入文本进行翻译，过滤 XHR 找到翻译 POST 请求。从请求中发现 URL 里的 `IG`、`IID`、`SFX`，表单里的 `fromLang`、`to`、`text`、`token`、`key`，以及请求头里的 `Origin`、`Referer`、`User-Agent`、`Content-Type`。
2. 多次翻译对比后发现 `token` 和 `key` 会变，因此必须从动态页面获取这些参数。
3. 翻译请求路径通常含 `ttranslatev3`。在 DevTools 的 Sources 中搜索 `ttranslatev3`，找到构造 URL 的 JS 片段，可以看到它读取 `IG`、`iid` 等变量；继续搜索 `params_AbusePreventionHelper`，找到变量赋值位置并确认参数含义。
4. 模拟浏览器抓取一次翻译首页，用正则动态提取这些参数，再带上浏览器风格的请求头发起 POST 翻译。

## 动态参数说明

- `IG`：页面生成的请求标识
- `params_AbusePreventionHelper`：数组 `[timestamp, token, ttl_ms]`，解析为 `key`、`token`、`ttl_ms`
- `data-iid`：请求标识，格式为 `translator.<id>`
- `params_RichTranslate`：翻译端点前缀，其中 `\u0026` 会还原为 `&`

`ParamProvider` 缓存有效参数；调用时若参数缺失、超过 `ttl_ms`，或服务器返回 HTTP 205/400，会自动抓取新参数后重试。所有临时参数只保存在内存中，不写入代码或缓存文件。

## 分层结构

```text
Btrans/
├── params.py       # 页面参数提取与动态缓存
├── client.py       # HTTP 客户端、压缩解码、JSON 解析
├── translator.py   # 公开翻译门面：校验、缓存、重试
├── cache.py        # 磁盘/内存缓存、TTL、统计与清理
├── exceptions.py   # 统一异常继承树
├── cli.py          # 命令行入口
└── __init__.py     # 导出 Translator
```

异常继承树：

```text
TranslationError
├── TranslationArgumentError
├── ParamError
│   └── ParamExtractionError
├── TranslationCacheError
└── TranslationClientError
    ├── InvalidParameterResponse
    ├── TranslationRequestError
    └── ResponseParseError
```

## 开发中遇到的困难

1. **定位动态参数**：翻译接口需要 `IG`、`token`、`key`、`IID`，直接请求缺少参数会失败，且参数会变化。通过浏览器抓包找到字段名，再用一次性探针脚本验证字段含义与完整请求流程。
2. **URL 编码与特殊符号**：文本可能包含 `&`、`%`、空格和中文，不能手工拼接请求体，统一构造字典交给 `requests` 自动编码：

```python
body = {
    "fromLang": from_lang,
    "to": to_lang,
    "text": text,
    "token": params.token,
    "key": params.key,
}

response = session.post(url, data=body)
```

3. **模拟浏览器请求**：只设置 `User-Agent` 不够，还需要 Cookie 与 Referer。`ParamProvider` 和 `TranslationClient` 共享同一个 `Session`，首页 GET 先建立 Cookie，POST 翻译时再携带完整浏览器特征。
4. **区分失败类型并自动恢复**：Bing 对失效参数返回 HTTP 205/400，网络异常会抛 `requests` 错误，坏响应会解析失败。因此建立异常边界：

```text
InvalidParameterResponse   <- HTTP 205/400
TranslationRequestError    <- 其它非 200 / 网络失败
ResponseParseError         <- 响应不是合法 JSON 或没有译文
TranslationArgumentError   <- 调用参数本身非法
```

## 注意

- Bing 偶尔返回空响应，公开门面对 `ResponseParseError` 自动重试一次，但仍可能偶发失败
- Windows 控制台输出中文时建议先设置 `PYTHONIOENCODING=utf-8`
- 本项目只用于技术学习与本地开发，请遵守目标网站的使用条款

GitHub：<https://github.com/zyp0714/bing-translate>
