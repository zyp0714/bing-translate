# bing-translate

用 Python 逆向实现微软 Bing 在线翻译（<https://cn.bing.com/translator>）的高可用翻译模块。


## 逆向思路
逆向思路：
1. 打开[bing翻译网页端](https://cn.bing.com/translator "点击访问")，按F12进入开发者工具，再输入中文进行翻译，过滤XHR找到有关翻译的POST请求。
从该请求中发现URL里的IG、IID、SFX
表单体里带 fromLang、to、text、token、key
请求头里有 Origin、Referer、User-Agent、Content-Type 等各种参数。
2. 通过多次翻译对比发现token 和 key 会变，要从动态页面获取这些参数的值。
3. 翻译请求的路径通常含 ttranslatev3。在 DevTools 的 Sources 里按 Ctrl+F 全局搜索 ttranslatev3，会找到一个构造 URL 的 JS 片段。这里能直接看到它用了 IG、iid 等变量。继续点变量名，或者搜索 params_AbusePreventionHelper，就能跳到赋值的地方。找到对应参数的含义。
4. 模拟浏览器抓一次翻译首页，用正则把这些参数动态提出来，再带上浏览器风格的请求头去 POST 翻译。
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

demo运行
```
uv run demo.py
```
demo它会自动演示：中英互译、自动语言识别、特殊字符、缓存命中、异常处理。

quick_translate运行
```
uv run quick_translate.py
```
quick_translate.py 是这个项目的命令行翻译工具。
目标语言默认 `auto`：中文输入译为英文，其他文本默认译为中文；交互模式中还可通过 `--to zh / en / auto` 与 `--from ...` 临时切换。

## 遇到的困难
1. 首先就是在网页上找动态参数。翻译接口要求 URL 和表单里带 IG、token、key、IID。直接请求接口时缺少这些参数会失败。找到字段名”靠的是浏览器抓包，确认字段含义和整套流程能不能跑通”靠的是一个一次性探针脚本。通过这个脚本找到了几个不断变化的参数。
2. URL 编码和特殊符号容易破坏请求。要求支持含 &、%、空格、中文的文本。不手工拼接，统一构造字典交给 requests
``` body = {
    "fromLang": from_lang,
    "to": to_lang,
    "text": text,
    "token": params.token,
    "key": params.key,
}

response = session.post(url, data=body)
```
3. 模拟浏览器发出请求。只模拟 User-Agent 不够，还需要 Cookie 和 Referer
ParamProvider 和 TranslationClient 共享同一个 Session
首页 GET 时先建立 Cookie
POST 翻译时设置完整浏览器特征
4. Bing 对失效参数会返回 HTTP 205/400，对网络异常会抛 requests 错误，对坏响应会解析失败。如果统一当普通失败处理，就无法自动恢复。
InvalidParameterResponse   <- HTTP 205/400
TranslationRequestError    <- 其它非 200 / 网络失败
ResponseParseError         <- 响应不是合法 JSON 或没有译文
TranslationArgumentError   <- 调用参数本身非法





GitHub：<https://github.com/zyp0714/bing-translate>
