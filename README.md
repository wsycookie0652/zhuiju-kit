# zhuiju-kit

自己维护的「追剧源」探活 + 看板工具集。数据引自 [awesome-zhuiju-free](https://github.com/laoma528/awesome-zhuiju-free)（CC BY 4.0），工程结构参考了它的做法，代码是自己写的极简版。

**它解决什么问题**：网上的 TVBox 配置地址 / IPTV 源列表大多没人管，过期了也没人删。这套东西每天探一次活，把「谁能连上」变成一张随时能看的表。

> ⚠️ 探活只证明**服务器还活着**，不证明**能出片**。配置里采集接口是否可用，得导入壳里点两集才知道。

---

## 目录结构

```
.
├── sources.txt                        # 你的源清单（URL | 名称 | 分类）
├── check_availability.py              # 并发探活 → reports/availability.json
├── build_dashboard.py                 # 拉上游数据 → 单文件 HTML 看板
├── reports/availability.json          # 探活报告（Actions 每天自动更新）
└── examples/
    └── check-availability.yml         # 每日自动探活的工作流模板
```

## 快速开始

```bash
# 1. 编辑源清单（每行一个，| 分隔，URL 里不要带 |）
vim sources.txt

# 2. 探活（16 并发，单源失败不影响其他）
python check_availability.py
# 🟢 小盒子4K      reachable    HTTP 200
# 🟡 某源          restricted   HTTP 403
# 🔴 某源          unreachable  (timeout)

# 3. 生成看板（拉到临时文件先看效果）
OUT=/tmp/dashboard.html python build_dashboard.py
```

`check_availability.py` 只依赖标准库，不需要 `pip install`。已经处理了两个坑：

- **中文域名**（如 `饭太硬.cc`）→ 自动做 IDN 编码 + path percent-encode，否则 urllib 直接抛异常
- **单源异常**（超时 / 证书错误 / DNS 失败）→ 只把这一条标红，不会炸掉整轮检测

## GitHub Actions

`examples/check-availability.yml` 是工作流模板。启用方式：GitHub 网页上新建文件 `.github/workflows/check-availability.yml`，把模板内容粘进去提交即可（也可以用 `git mv` 本地移动后推送）。

> 为什么放在 `examples/` 而不是直接放 `.github/workflows/`：写入工作流文件需要 token 具备 `workflow` 权限，普通 `public_repo` token 会被 GitHub 拒绝。放模板目录，谁 clone 都能自行启用。

跑起来之后每天 01:00 UTC（北京 09:00）执行一次，也支持在 Actions 页面手动触发。

**唯一需要手动做的设置**：仓库 → Settings → Actions → General → Workflow permissions → 选 **Read and write permissions**。不设的话最后一步 `git push` 会 403。

报告会提交到 `reports/availability.json`，字段：

```json
{
  "generated_at": "2026-11-15T01:00:12.345Z",
  "summary": { "reachable": 9, "restricted": 0, "unreachable": 0 },
  "results": [
    { "name": "小盒子4K", "url": "...", "status": "reachable",
      "http_status": 200, "response_ms": 340, "attempts": 1,
      "checked_at": "2026-11-15T01:00:05.120Z", "error": null }
  ]
}
```

状态判定：`2xx/3xx` → 🟢 reachable；`401/403/429/451` → 🟡 restricted（有响应但被风控拦住）；其他 → 🔴 unreachable。

## 看板

`build_dashboard.py` 会拉上游的 `resources/resources.json` + `reports/availability.json`，生成一个零依赖的单文件 HTML（内嵌数据，双击就能打开）：

- 搜索（名称 / 简介 / 标签 / 域名）+ 9 个分类筛选
- 状态徽章（🟢🟡🔴）+ HTTP 码 + 响应毫秒
- 四维风险标记（版权 / 安全 / 隐私 / 付费）
- TVBox 配置地址一键复制

`OUT` 环境变量控制输出路径，默认 `./dashboard.html`。写入是原子的（先写 `.tmp` 再 `os.replace`），所以可以放心让定时任务覆盖正在被访问的文件。

## 部署到自己的 NAS（可选）

```yaml
services:
  kit-web:                      # 静态服务
    image: python:3.12-alpine
    command: ["-m", "http.server", "80", "--directory", "/site"]
    ports: ["8789:80"]
    volumes: ["./site:/site:ro"]
    restart: unless-stopped

  kit-builder:                  # 每 6 小时重建看板
    image: python:3.12-alpine
    entrypoint: ["/bin/sh", "-c"]
    command: ["while true; do python -u /app/build_dashboard.py; sleep 21600; done"]
    environment:
      - OUT=/site/index.html
      - PYTHONUNBUFFERED=1
    volumes:
      - "./site:/site"
      - "./build_dashboard.py:/app/build_dashboard.py:ro"
    restart: unless-stopped
```

> 如果你在国内 NAS 上跑，注意两点：① 优先 IPv4（部分容器内 DNS 只返回 IPv6，请求会静默挂死）；② 改了 compose 配置一定要 `docker compose up -d --force-recreate`，否则跑的还是旧命令。

## 数据来源与署名

- 资源数据：[laoma528/awesome-zhuiju-free](https://github.com/laoma528/awesome-zhuiju-free)，**CC BY 4.0**
- 探活方法论参考同项目（JSON 主数据 + Schema 校验 + 每日 Actions + 状态徽章）

## 免责声明

本仓库只提供**链接可达性检测工具**，不存储、不托管、不分发任何音视频内容。`sources.txt` 中的地址均为第三方公开链接，请自行判断其合法性与安全性。

请支持正版。因使用第三方源产生的任何问题由使用者自行承担。
