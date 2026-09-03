# Bing Translate 项目交接文档

本文档写给一个没有本项目上下文的新对话。请先完整阅读本文件，再结合仓库源码工作。

## 1. 项目要做什么

项目来自一份 Python 测试题：逆向微软 Bing 在线翻译网页端，用 Python 实现高可用翻译模块。

核心要求：

- 不允许硬编码 Bing 的临时鉴权参数；
- 每次启动或参数失效时，动态请求 Bing 翻译首页，从 HTML/JavaScript 中提取参数；
- 提供公开翻译 API，支持中文、英文和自动识别；
- 请求时维护 Cookie、真实浏览器请求头，并处理 `br/gzip` 压缩响应；
- 设计清晰异常继承树；
- 支持本地缓存、缓存 TTL、缓存统计和清理；
- 提供单元测试、demo、README，并上传到 GitHub。

题目约定的公开调用形式：

```python
from Btrans import Translator

translator = Translator(enable_cache=True, cache_dir="./my_cache")
result_zh = translator.translate("Hello, world!", from_lang="en", to_lang="zh")
```

## 2. 当前仓库与 Git 状态

- 本地项目目录：`D:\daima\bing_translate`
- GitHub 公共仓库：`https://github.com/zyp0714/bing-translate`
- 默认分支：`main`
- 当前远端已有初始提交：`5fc58e3 Initial commit`
- 该初始提交只包含脚手架：
  - `.python-version`
  - `README.md`（内容为空）
  - `pyproject.toml`
  - `src/bing_translate/__init__.py`（目前只是 Hello 示例）
  - `uv.lock`
- `Btrans/`、`scratch/` 等后续新增文件目前都还没有提交。
- 环境中 Python 版本要求 `>=3.10`，仓库内已有 `.venv`。

## 3. 已经完成的内容

### 3.1 端到端探针

文件：`scratch/probe_bing.py`

作用：临时验证整条链路，不属于最终正式代码。

已验证结果：

- 能抓取 Bing 翻译首页；
- 能从首页提取动态参数；
- 能发起真实翻译 POST；
- 实测双向翻译成功：

```text
zh: 你好，世界！ | detected: en
en: Hello, world! | detected: zh-Hans
```

### 3.2 动态参数模块

文件：`Btrans/params.py`

已实现：

- `BingPageParams`：
  - 保存 `IG/token/key/ttl_ms/iid/endpoint_prefix/fetched_at`；
  - `from_html()` 从首页 HTML 解析参数；
  - `is_expired()` 判断 TTL；
  - `build_url()` 拼翻译端点。
- `ParamProvider`：
  - 缓存当前有效参数；
  - `get()`：无参数或过期时自动抓首页；
  - `refresh()`：强制刷新；
  - `invalidate()`：参数失效后丢弃；
  - 对外暴露 `session`，供后续 HTTP 请求复用 Cookie。
- 参数全部动态提取，代码中没有硬编码 token/key。

### 3.3 低层 HTTP 客户端

文件：`Btrans/client.py`

已实现：

- `TranslationClient`：发起真实翻译 POST；
- 使用 `ParamProvider` 返回的参数构造请求体；
- 与首页抓取共用同一个 Session，保持 Cookie；
- 支持手动处理 `br/gzip/deflate` 响应；
- `TranslationResult`：返回译文和来源语言；
- 已定义 client 层错误类型；
- 真实网络翻译验证通过。

## 4. 设计思路

### 4.1 分层结构

建议最终分层：

```text
Translator（业务门面）
    ↓
ParamProvider（动态参数）
    ↓
TranslationClient（HTTP POST）
    ↓
Bing 服务器
```

各模块职责：

| 模块 | 职责 |
|---|---|
| `params.py` | 获取并管理动态鉴权参数 |
| `client.py` | 发起请求、处理压缩、解析响应 |
| `translator.py` | 对外 API、缓存、重试和异常转换 |
| `cache.py` | 本地翻译缓存 |
| `exceptions.py` | 统一异常树 |

### 4.2 Bing 请求链路

已确认的真实请求结构：

- 首页地址：`https://cn.bing.com/translator`
- 翻译端点：`/ttranslatev3?isVertical=1&`
- URL 会追加：`IG`、`IID`、`SFX`
- POST 表单字段：

```text
fromLang
to
text
token
key
```

- 鉴权参数来源于首页：
  - `IG`
  - `params_AbusePreventionHelper[0]` → `key`（毫秒时间戳）
  - `params_AbusePreventionHelper[1]` → `token`
  - `params_AbusePreventionHelper[2]` → `ttl_ms`
- `IID` 来自页面 `data-iid`，例如 `translator.5023`

关键结论：

- `IG/token/key` 每次抓首页都可能变化，必须动态获取；
- `ttl_ms` 表示有效时间窗；
- 翻译不同文本不会改变鉴权参数，只改变 `text`；
- 收到 HTTP 205/400 或解析失败时，应丢弃参数并重新抓取一次。

### 4.3 自愈流程

预期正式 `Translator` 内部流程：

1. 校验文本非空、语言方向合理；
2. 查询缓存，命中则返回；
3. 调用 `ParamProvider.get()` 获取参数；
4. 调用 `TranslationClient.translate()`；
5. 成功则写缓存并返回；
6. 捕获 `InvalidParameterResponse`：
   - 调用 `ParamProvider.invalidate()`
   - 重新获取参数
   - 无感重试一次
7. 仍失败则抛出统一异常。

### 4.4 缓存设计

- 缓存 key：由原文、源语言、目标语言共同计算，例如 SHA-256；
- 默认 TTL 参考题目建议：24 小时；
- 支持自定义缓存目录、禁用缓存；
- 提供 `get_cache_size()` 和 `clear_cache()`；
- 单元测试时缓存应可替换为内存实现。

### 4.5 语言方向

页面内实际语言代码：

- 自动检测：`auto-detect`
- 简体中文：`zh-Hans`
- 英文：`en`

题目公开接口写的是 `zh/en/auto`，因此 `Translator` 需要做一层代码映射，例如：

```text
auto -> auto-detect
zh   -> zh-Hans
en   -> en
```

## 5. 尚未完成的内容

按依赖顺序列出：

1. `Btrans/exceptions.py`
   - 统一异常继承树，根为 `TranslationError`
   - 将 `params.py`、`client.py` 中的局部异常迁移过去
2. `Btrans/cache.py`
   - TTL 缓存
   - 缓存读写、清理、统计
3. `Btrans/translator.py`
   - 实现 `Translator` 门面
   - 实现 `translate()`、`get_cache_size()`、`clear_cache()`
   - 缓存、刷新重试编排
4. `Btrans/__init__.py`
   - 导出 `Translator`
5. `demo.py`
6. `tests/`
   - 空输入
   - 基本翻译（mock 网络）
   - 缓存读写和过期
   - 参数失效后自动刷新
   - 压缩响应解析
7. `README.md`
8. 项目结构/打包决策
   - 当前 `pyproject.toml` 使用 `src/bing_translate`；
   - 题目要求 `from Btrans import Translator`；
   - 需要确定是保留 `src/bing_translate`，还是让 `Btrans` 成为正式包；
   - 修改 pyproject 时保证本地和安装后都能导入 `Btrans`。
9. 清理临时文件并提交推送到 GitHub

## 6. 下一步优先完成

推荐顺序：

1. 创建 `Btrans/exceptions.py`；
2. 创建 `Btrans/cache.py`；
3. 创建 `Btrans/translator.py`；
4. 创建 `Btrans/__init__.py` 并导出 `Translator`；
5. 用下面方式做冒烟验证：

```python
from Btrans import Translator

translator = Translator(enable_cache=False)
print(translator.translate("Hello, world!", from_lang="en", to_lang="zh"))
```

## 7. 验证方式

真实网络验证命令示例：

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -c "from Btrans.params import ParamProvider; from Btrans.client import TranslationClient; p=ParamProvider(); c=TranslationClient(p); print(c.translate('Hello, world!', 'en', 'zh-Hans'))"
```

注意：

- 中文输出需要设置 `PYTHONIOENCODING=utf-8`；
- 真实请求需要网络能访问 `cn.bing.com`；
- 普通单元测试不要依赖真实网络，应 mock 响应。

## 8. 临时文件与清理

以下文件是分析过程产物，不要提交到 Git：

- `scratch/page.html`
- `scratch/cookies.txt`
- `scratch/rp_*.js`
- `scratch/translator.js`
- `.tmp_python_test.pdf`
- `.tmp_pdf_page1.png`
- `.tmp_pdf_page2.png`
- `Btrans/__pycache__/`

建议后续补充 `.gitignore`：

```text
__pycache__/
*.py[cod]
.venv/
scratch/
```

`scratch/probe_bing.py` 可作为开发参考，但最终提交物中建议删除或明确标记为开发脚本。

## 9. 已知注意事项

- 当前 `Btrans/` 和 `scratch/` 都是未跟踪状态；
- 当前机器/Codex 沙箱无法直连 `github.com` 的 git 端口，但 REST API 可用；必要时可通过 GitHub API 推送，或让用户在普通终端执行 `git push`；
- Bing 首页结构可能变化，参数提取正则需要保留“失效后刷新”能力；
- 本项目已有公共仓库，后续提交不要覆盖仓库 owner/URL；
- 本交接文档属于开发过程记录，最终对外发布前可删除或并入 README。
