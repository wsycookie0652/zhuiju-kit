# zhuiju-kit

自己维护的「追剧源」探活 + 看板工具集。数据引自 [awesome-zhuiju-free](https://github.com/laoma528/awesome-zhuiju-free)（CC BY 4.0），工程结构参考了它的做法，代码是自己写的极简版。

**它解决什么问题**：网上的 TVBox 配置地址 / IPTV 源列表大多没人管，过期了也没人删。这套东西每天探一次活，把「谁能连上」变成一张随时能看的表。

> ⚠️ 探活只证明**服务器还活着**，不证明**能出片**。配置里采集接口是否可用，得导入壳里点两集才知道。

**为什么要两个出口测**：单个网络位置的探活结果会骗人。同一个 VMA 直播源，在你家宽带是 🔴（TLS 握手被中途重置），在 GitHub Actions 的海外节点是 🟢。只有两边都红，才基本能判定「源真的挂了」。所以看板会把**本机/NAS 视角**和**Actions 视角**并排显示。

---

## 目录结构

```
├── sources.txt                        # 你的源清单（26 个：TVBox 配置 / IPTV / 字幕 / 网盘 / 磁力）
├── check_availability.py              # 并发探活 → reports/availability.json
├── build_dashboard.py                 # 拉上游数据 + 双视角对照 → 单文件 HTML 看板
├── reports/availability.json          # 探活报告（Actions 每天自动更新）
└── .github/workflows/
    └── check-availability.yml         # 每天 09:00 (北京) 自动跑
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

`.github/workflows/check-availability.yml` 已就绪，每天 01:00 UTC（北京 09:00）跑一次，也支持在 Actions 页面手动触发。

**唯一需要手动做的设置**：仓库 → Settings → Actions → General → Workflow permissions → 选 **Read and write permissions**。不设的话最后一步 `git push` 会 403。

报告会提交到 `reports/availability.json`，字段：

```json
{
  "generated_at": "2026-11-15T01:00:12.345Z",
  "summary": { "reachable": 24, "restricted": 0, "unreachable": 2 },
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

- 128 条上游资源：搜索（名称 / 简介 / 标签 / 域名）+ 9 个分类筛选
- 状态徽章（🟢🟡🔴）+ HTTP 码 + 响应毫秒
- 四维风险标记（版权 / 安全 / 隐私 / 付费）
- TVBox 配置地址一键复制
- **顶部「我的源 · 双视角对照」区块**：你自己的 26 个源，每个同时显示本机/NAS 与 Actions 两次探活结果

`OUT` 环境变量控制输出路径，默认 `./dashboard.html`。写入是原子的（先写 `.tmp` 再 `os.replace`），所以可以放心让定时任务覆盖正在被访问的文件。

拉数据有两级容错：`raw.githubusercontent.com`（8s 超时）失败就换 `cdn.jsdelivr.net`，再失败换 `ghfast.top`——国内网络下 raw 被重置是常态。

### 双视角怎么读

| 判定 | 含义 | 该怎么办 |
|---|---|---|
| 🟢 双绿 | 两个出口都通 | 放心用 |
| 🟡 仅 Actions 绿 | 你的网络连不上，源本身活着 | 本机 TLS 被干扰 / 需要代理；源别删 |
| 🔵 仅本机绿 | Actions 节点连不上 | 多半是 Github 节点被目标站风控，忽略即可 |
| 🔴 双向失败 | 两个出口都红 | 大概率真挂了，可以换源 |

Actions 那份报告通过 jsDelivr 读取，可能比实际运行时间晚几十分钟到几小时（CDN 缓存），页面顶部会显示它的 `generated_at`，自己判断新鲜度。想关掉对照：`GH_REPORT="" python build_dashboard.py`；想指定别的报告：`GH_REPORT=https://... python build_dashboard.py`。

## 部署到自己的 NAS（可选）

```yaml
services:
  kit-web:                      # 静态服务
    image: python:3.12-alpine
    command: ["-m", "http.server", "80", "--directory", "/site"]
    ports: ["8789:80"]
    volumes: ["./site:/site:ro"]
    restart: unless-stopped

  kit-builder:                  # 每 6 小时：先探活，再重建看板
    image: python:3.12-alpine
    entrypoint: ["/bin/sh", "-c"]
    command:
      - "while true; do python -u /work/check_availability.py; python -u /work/build_dashboard.py; sleep 21600; done"
    environment:
      - OUT=/site/index.html
      - PYTHONUNBUFFERED=1
    volumes:
      - "./site:/site"
      - "./:/work:ro"          # 注意：别挂到 /app，会覆盖镜像自带的 python 环境
    restart: unless-stopped
```

> 如果你在国内 NAS 上跑，注意两点：① 优先 IPv4（部分容器内 DNS 只返回 IPv6，请求会静默挂死）；② 改了 compose 配置一定要 `docker compose up -d --force-recreate`，否则跑的还是旧命令。

## 数据来源与署名

- 资源数据：[laoma528/awesome-zhuiju-free](https://github.com/laoma528/awesome-zhuiju-free)，**CC BY 4.0**
- 探活方法论参考同项目（JSON 主数据 + Schema 校验 + 每日 Actions + 状态徽章）

## 免责声明

本仓库只提供**链接可达性检测工具**，不存储、不托管、不分发任何音视频内容。`sources.txt` 中的地址均为第三方公开链接，请自行判断其合法性与安全性。

请支持正版。因使用第三方源产生的任何问题由使用者自行承担。
