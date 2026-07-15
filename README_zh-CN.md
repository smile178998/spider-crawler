# Modern Web Scraper

基于 Playwright 的 Web 爬虫，配有 FastAPI 界面，并提供三层可编程抓取栈（HTTP → 浏览器 → 隐秘浏览器）。可渲染重度 JS 页面，提取结构化内容（正文、评论、视频、图片、元数据），支持本地媒体下载与页面内播放。

**语言 / Language：** [English](README.md) | **简体中文**

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey) ![Version](https://img.shields.io/badge/version-1.3.0-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## 使用演示

![使用演示](demo.gif)

*输入 URL → 打开高级选项 → 开始抓取 → 查看正文、视频、日志与选择器选项卡。*

![截图](image.png)

---

## 架构一览

| 层级 | 模块 | 作用 |
|------|------|------|
| **Web UI / SSE API** | `app.py` + `scraper_core.py` | 面向浏览器与视频站的完整抓取管道 |
| **第一层 — HTTP** | `fetcher.py` | 快速隐秘请求（`curl_cffi`）：TLS 指纹、标头、可选 HTTP/3 |
| **第二层 — 浏览器** | `dynamic_fetcher.py` | Playwright Chromium / Google Chrome，适合 JS/SPA |
| **第三层 — 隐秘** | `stealthy_fetcher.py` | Patchright/Playwright + 指纹伪装 + Cloudflare 挑战流程 |
| **Session** | `sessions.py` | `FetcherSession` / `DynamicSession` / `StealthySession` — Cookie + 状态 |
| **代理** | `proxy_rotator.py` | 轮询 / 随机 / 自定义轮换；支持单次请求覆盖 |
| **屏蔽** | `request_blocking.py` | `blocked_domains` + `block_ads`（约 3500 个追踪域名） |

---

## 功能特性

### 内容提取（Web UI）
- 真实浏览器渲染（Playwright）— 支持 JS、SPA、懒加载
- 自动正文/评论识别 + 可选 CSS 覆盖
- 视频与图片提取（含 `data-src` 等懒加载属性）
- 智能图片过滤（图标、精灵图、垃圾缩略图）
- `<meta>` 元数据；导出 TXT / JSON

### 视频平台（`video_platforms/`）
- 自动识别：**哔哩哔哩**、**YouTube**、**Vimeo**、**TikTok**、**抖音**、**Twitter/X**、**Twitch**、**Dailymotion**、**Niconico**
- **B 站** — `__INITIAL_STATE__`、`__playinfo__`、WBI 评论分页、DASH 流
- **其他站** — Open Graph、JSON-LD、`ytInitialPlayerResponse`、DOM `<video>`
- 结果字段：`platform`、`platform_data`、精选图（封面 / 头像 / 首帧）
- 已知视频 URL 自动跳过通用选择器

### 媒体下载与播放
- 自动下载到 `downloads/`；魔数校验（拒绝 HTML 错误页）
- **ffmpeg** 转封装：B 站 DASH（`.m4s` → 可播放 `.mp4`）
- **Videos** 选项卡 — 内嵌 `<video>`，经 `/downloads/...` 提供正确 MIME

### 记住登录
- 持久化 Chrome 配置目录 `.chrome_profile/`
- Visible 模式登录一次，全站复用
- Cookie 字段可覆盖已保存会话

### 智能自动选择器
- 启发式 DOM 评分 + 稳定 CSS 生成
- AI 兜底（OpenAI 兼容：OpenAI、DeepSeek、Ollama）
- **Selectors** 选项卡 — 方法、置信度、一键应用

### 反检测与网络
- 系统 Chrome + `playwright-stealth` + 指纹补丁
- 模拟人类操作；挑战页等待；多策略重试
- UI / `SCRAPER_PROXY` / `HTTP_PROXY` 代理；失效环境代理自动跳过
- 全 Session **ProxyRotator**；浏览器 Fetcher **域名/广告屏蔽**
- 端口占用时自动换到 8001+

---

## 项目结构

```
spaider_crawler/
├── app.py                 # FastAPI + SSE API + /downloads
├── scraper_core.py        # 主 Playwright 抓取管道
├── selector_engine.py     # 启发式 + AI 选择器发现
├── media_downloader.py    # 图片/视频下载、ffmpeg、MIME
├── fetcher.py             # 隐秘 HTTP（curl_cffi）
├── dynamic_fetcher.py     # Playwright DynamicFetcher
├── stealthy_fetcher.py    # StealthyFetcher + CF 挑战流程
├── session_store.py       # Cookie / 状态 JSON 工具
├── sessions.py            # Session 统一导出
├── proxy_rotator.py       # 代理轮换策略
├── request_blocking.py    # 域名 + 广告请求屏蔽
├── ad_domains.py          # 内置追踪域名列表加载
├── image_utils.py         # 图片 URL 清理 / 垃圾过滤
├── data/ad_domains.txt    # 约 3500 个广告/追踪主机（Peter Lowe）
├── video_platforms/       # 多平台视频提取
├── templates/index.html
├── static/css|js/
├── scripts/start.ps1      # Windows 启动脚本
├── scripts/scrape_video.py
├── requirements.txt
└── .env.example
```

---

## 环境要求

- Python 3.10+
- Google Chrome（可选，推荐）
- **ffmpeg**（可选，用于 DASH → MP4）
- **patchright**（可选，加强 `StealthyFetcher`）

---

## 安装

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium
```

可选隐秘引擎：

```bash
pip install patchright
python -m patchright install chrome
```

按需复制 `.env.example` → `.env`：

```env
OPENAI_API_KEY=sk-your-key-here
# SCRAPER_PROXY=http://127.0.0.1:7890
# BILI_COOKIE=SESSDATA=...; bili_jct=...
```

---

## 快速开始

**Windows：**

```powershell
.\scripts\start.ps1
```

**或：**

```bash
python app.py
# python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

打开 `http://127.0.0.1:8000/`（或终端打印的端口）。页眉应显示 **v1.3.0**。

### B 站示例

| 选项 | 建议值 |
|------|--------|
| Remember login | 开（首次用 Visible） |
| JS wait | `8000` ms |
| 自动滚动 / 系统 Chrome / Auto-download | 开 |
| Smart auto-selector | 关（视频站自动处理） |

### YouTube 示例

同上；拉取流地址建议 Visible。仅在网络需要时填写 Proxy。

### 命令行

```bash
python scripts/scrape_video.py "https://www.bilibili.com/video/BV1yk7X6KEz4" output.json
```

---

## Web 界面选项

| 选项 | 说明 |
|------|------|
| 正文 / 评论选择器 | CSS；留空则自动 |
| Remember login | `.chrome_profile/` 持久会话 |
| Cookie | 可选覆盖（`k=v; ...`） |
| Proxy | `http://` / `socks5://`；空=直连 |
| JS wait (ms) | 加载后等待 500–30000 |
| Browser mode | Auto / Headless / Visible |
| Max retries | 0–4 次换策略重试 |
| Use system Chrome | 优先系统 Chrome |
| Simulate human | 鼠标与滚动噪声 |
| Block resources | 跳过图片/字体（可能更像机器人） |
| Auto-download | 保存媒体；Videos 选项卡播放 |
| Smart auto-selector / AI | 发现 CSS；AI 需 API Key |

**需登录站点：** Remember login + Visible + 系统 Chrome。  
**视频站：** 选择器留空；开启 Auto-download。

---

## 可编程 Fetcher

### 第一层 — `Fetcher`（HTTP）

```python
from fetcher import Fetcher, FetcherSession

r = Fetcher.get("https://example.com", stealthy_headers=True, impersonate="chrome")
r = Fetcher.get("https://http3-capable.example", http3=True)

with FetcherSession(session_file=".sessions/api.json") as s:
    s.get("https://example.com/login")
    s.state["user"] = "alice"
    s.post("https://example.com/api", json_body={"q": 1})
```

基于 `curl_cffi` 做 TLS/JA3 伪装；未安装时回退 `urllib`。

### 第二层 — `DynamicFetcher`（浏览器）

```python
from dynamic_fetcher import DynamicFetcher, DynamicSession

r = DynamicFetcher.fetch(
    "https://spa.example.com",
    real_chrome=True,
    network_idle=True,
    wait=1500,
    wait_selector="main",
    block_ads=True,
    blocked_domains={"metrics.vendor.com"},
)

with DynamicSession(real_chrome=True, session_file=".sessions/web.json") as s:
    s.fetch("https://example.com")
    s.fetch("https://example.com/account")  # Cookie 保留
```

### 第三层 — `StealthyFetcher`（反机器人）

```python
from stealthy_fetcher import StealthyFetcher, StealthySession

r = StealthyFetcher.fetch(
    "https://protected.example",
    solve_cloudflare=True,
    hide_canvas=True,
    block_webrtc=True,
    block_ads=True,
    real_chrome=True,
    timeout=60000,
)
```

> Cloudflare 流程是在真实浏览器里自动过挑战页 UI，并非破解验证码密码学。

### Session、代理轮换、屏蔽

```python
from sessions import FetcherSession, DynamicSession, StealthySession
from sessions import ProxyRotator, random_rotation

# 统一 API：get/set/clear cookies、save/load/snapshot/restore、state={}
with FetcherSession(session_file=".sessions/api.json") as s:
    s.set_cookies({"token": "x"}, url="https://example.com")
    s.save()

rotator = ProxyRotator([
    "http://1.2.3.4:8080",
    {"server": "http://5.6.7.8:8080", "username": "u", "password": "p"},
])
with FetcherSession(proxy_rotator=rotator) as s:
    s.get("https://example.com/a")              # #1
    s.get("https://example.com/b")              # #2
    s.get("https://example.com/c", proxy=None)  # 本请求直连
    print(s.last_proxy)

# 也支持随机 / 自定义：
# ProxyRotator(proxies, strategy=random_rotation)
```

同一 Session 不要同时设静态 `proxy=` 与 `proxy_rotator=`。单次请求的 `proxy=` 优先级最高。

---

## API 参考

### `GET /api/health`

```json
{
  "status": "ok",
  "version": "1.3.0",
  "features": [
    "video_platforms", "wbi_comments", "download_media", "saved_profile",
    "stealth_fetcher", "dynamic_fetcher", "stealthy_fetcher",
    "session_manager", "proxy_rotator", "request_blocking"
  ]
}
```

### `GET /downloads/{path}`

以正确 MIME（如 `video/mp4`）提供已下载媒体。

### `POST /api/scrape`

SSE 流。请求体字段：

| 字段 | 默认 | 说明 |
|------|------|------|
| `url` | *必填* | 目标 URL |
| `text_selector` / `comment_selector` | `""` | CSS 覆盖 |
| `cookie` | `""` | 认证 Cookie |
| `proxy` | `""` | 代理地址 |
| `wait_ms` | `3500` | JS 等待（500–30000） |
| `scroll` | `true` | 自动滚动 |
| `use_chrome` | `true` | 系统 Chrome |
| `headless` | `"auto"` | `auto` / `hidden` / `visible` |
| `max_retries` | `2` | 0–4 |
| `simulate_human` | `true` | 鼠标/滚动 |
| `block_resources` | `false` | 跳过图片/字体 |
| `auto_selector` / `auto_selector_ai` | `true` | 智能选择器 |
| `ai_api_key` / `ai_base_url` / `ai_model` | `""` | LLM 覆盖 |
| `download_media` | `true` | 保存到 `downloads/` |
| `use_saved_profile` | `true` | `.chrome_profile/` |

**SSE 事件：** `log`、`ping`、`done`、`error`。校验失败 → HTTP `422`。

```python
import json, urllib.request
body = json.dumps({
    "url": "https://www.bilibili.com/video/BV1yk7X6KEz4",
    "wait_ms": 8000, "use_chrome": True,
    "download_media": True, "use_saved_profile": True,
    "auto_selector": False,
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/scrape", data=body,
    headers={"Content-Type": "application/json"}, method="POST",
)
with urllib.request.urlopen(req, timeout=300) as resp:
    for line in resp.read().decode().splitlines():
        if line.startswith("data: "):
            print(line[6:])
```

---

## API 输出（`done`）

```json
{
  "url": "https://www.bilibili.com/video/BV1yk7X6KEz4",
  "title": "视频标题",
  "platform": "bilibili",
  "text_paragraphs": ["播放 ...", "UP主: ..."],
  "comments": ["用户: 评论"],
  "videos": ["/downloads/.../videos/video.mp4"],
  "images": ["https://.../cover.jpg"],
  "meta": { "video_platform": "bilibili", "bilibili_bvid": "BV1yk7X6KEz4" },
  "platform_data": {
    "platform": "bilibili",
    "video_streams": [{ "url": "...", "width": 1920 }],
    "audio_streams": [{ "url": "..." }],
    "comments": ["用户: 评论"]
  },
  "downloads": {
    "dir": ".../downloads/...",
    "web_dir": "/downloads/...",
    "images": [{ "web_path": "/downloads/.../images/001.jpg" }],
    "videos": [{ "web_path": "/downloads/.../videos/video.mp4", "playable": true, "mime": "video/mp4" }]
  }
}
```

选项卡：正文 · 评论 · **Videos** · 图片 · **Selectors** · 元数据 · 日志。

---

## 故障排除

| 问题 | 处理 |
|------|------|
| Playwright 无法启动 | `python -m playwright install chromium` |
| 8000 端口占用 | 用 `.\scripts\start.ps1` 或终端显示的端口（8001+） |
| `ERR_CONNECTION_CLOSED` | 清除失效的 `HTTP_PROXY`；尝试 Visible + 系统 Chrome |
| Cloudflare / WAF | Visible + Chrome + 代理；或 `StealthyFetcher(solve_cloudflare=True)` |
| SPA 内容为空 | 加大 JS wait；开启自动滚动 |
| 验证码 | Visible + Remember login；手动过一次 |
| 视频无法播放 | 开启 Auto-download；DASH 需安装 **ffmpeg** |
| 下载到的是 HTML | 需登录 / 流地址过期 — Visible + 已保存登录 |
| B 站评论很少 | Remember login 或配置 `BILI_COOKIE` |
| Profile 被锁定 | 关闭占用 `.chrome_profile/` 的其他 Chrome/爬虫 |
| 未安装 Patchright | 可选：`pip install patchright && python -m patchright install chrome` |

---

## 使用说明与责任

- 仅抓取你有权访问的内容，遵守 `robots.txt` 与网站条款。
- 用于学习与正当研究 — 不是万能验证码 / WAF 绕过工具。
- 只使用自己的 Cookie/会话，勿滥用他人凭证。
- 视频流可能受版权保护，请合法合理使用数据。

---

## 许可证

MIT License — 见 [LICENSE](LICENSE)。
