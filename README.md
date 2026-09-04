# bing-translate

用 Python 逆向实现微软 Bing 在线翻译（<https://cn.bing.com/translator>）的高可用翻译模块。项目动态提取页面鉴权参数，不硬编码任何 `IG`、`token`、`key`，并提供本地缓存、TTL、统计清理、异常继承树、CLI、demo 与单元测试。

## 功能

- 支持 `zh`、`en`、`auto` 三种源语言与 `zh`、`en` 目标语言
- 模拟真实浏览器请求头、Cookie 会话与 `br` / `gzip` / `deflate` 压缩响应处理
- 自动抓取并缓存 Bing 页面动态参数，参数失效后自动重试刷新
- 磁盘缓存 + TTL，默认 24 小时；提供清理、统计与禁用开关
- 完整异常继承树，缓存损坏或请求失败时可自动降级/重试
- 提供 `bing-translate` 命令、`demo.py` 与可安装的公开 API

## 逆向思路与请求链路

翻译端点是网页加载 `params_RichTranslate` 后暴露出的接口，请求体中的 `IG`、`IID`、`key`、`token` 来自页面脚本，会随时间失效。因此客户端每次启动时先抓取首页并解析这些字段，用同一个 `requests.Session` 保持 Cookie，再提交翻译请求。

请求链路：

1. `GET https://cn.bing.com/translator` 获取页面 HTML/JS
2. 从页面提取 `IG`、`params_AbusePreventionHelper`、`data-iid`、`params_RichTranslate`
3. `POST` 翻译端点，携带浏览器风格的请求头与表单参数
4. 手动解码 `br` / `gzip` / `deflate` 响应体并解析翻译 JSON
5. 结果先写本地缓存，之后相同文本与语言方向直接命中缓存

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

## 安装

需要 Python >= 3.10。推荐使用 uv：

```powershell
uv sync
```

也可以使用 pip 安装当前项目：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
```

安装后可编辑安装目录外直接使用：

```python
from Btrans import Translator
```

## 使用

Python API：

```python
from Btrans import Translator

translator = Translator(enable_cache=True, cache_dir="./my_cache")
result = translator.translate("Hello, world!", from_lang="en", to_lang="zh")

print(result.text)
print(result.detected_language)
```

命令行（安装后为 `bing-translate`，开发阶段也可直接运行 `quick_translate.py`）：

```powershell
bing-translate "Hello, world!"
bing-translate "我喜欢用 Python 写程序" --to en
bing-translate "Bonjour" --from auto --to zh
bing-translate --help
```

目标语言默认 `auto`：中文输入译为英文，其他文本默认译为中文；交互模式中还可通过 `--to zh / en / auto` 与 `--from ...` 临时切换。

运行演示：

```powershell
.venv\Scripts\python.exe demo.py
```

## 运行测试

全部测试使用 mock，不依赖真实网络：

```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

真实翻译验证需要能够访问 `cn.bing.com`：

```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python.exe -c "from Btrans import Translator; t=Translator(enable_cache=False); print(t.translate('Hello, world!', from_lang='en', to_lang='zh'))"
```

## 注意

- Bing 偶尔返回空响应，公开门面对 `ResponseParseError` 自动重试一次，但仍可能偶发失败
- Windows 控制台输出中文时建议先设置 `PYTHONIOENCODING=utf-8`
- 本项目只用于技术学习与本地开发，请遵守目标网站的使用条款

GitHub：<https://github.com/zyp0714/bing-translate>
