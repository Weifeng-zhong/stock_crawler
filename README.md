# 沪深交易所日成交数据系统

自动获取上海证券交易所和深圳证券交易所每日成交额（股票 + 基金），提供 Web 查询、批量追溯、定时邮件推送功能。

---

## 目录

- [项目结构](#项目结构)
- [功能概述](#功能概述)
- [技术架构](#技术架构)
- [数据源详情](#数据源详情)
- [快速开始（本地开发）](#快速开始本地开发)
- [部署指南](#部署指南)
- [GitHub Secrets 配置](#github-secrets-配置)
- [GitHub Actions 工作流](#github-actions-工作流)
- [依赖清单](#依赖清单)
- [常见问题](#常见问题)
- [扩展指南](#扩展指南)

---

## 项目结构

```
stock_tool/
├── app.py                           # Streamlit 网页应用（入口）
├── daily_fetch.py                   # 数据获取 + 邮件发送脚本
├── requirements.txt                 # Python 依赖
├── config.json                      # 订阅配置（由网页端写入，Actions 读取）
├── .github/workflows/
│   └── send_daily.yml              # GitHub Actions 定时任务
└── README.md                       # 本文件
```

### 文件职责

| 文件 | 运行环境 | 职责 |
|------|---------|------|
| `app.py` | Streamlit Cloud | Web UI，单日/批量查询，订阅管理 |
| `daily_fetch.py` | GitHub Actions | 获取 API 数据，SMTP 发邮件 |
| `send_daily.yml` | GitHub Actions | 定时触发（cron）+ 支持 workflow_dispatch |
| `config.json` | GitHub 仓库 | 存储订阅邮箱列表、最后发送日期 |
| `requirements.txt` | 两者 | 锁定依赖版本 |

---

## 功能概述

### 1. Web 查询（Streamlit Cloud）

**网址：** https://stockcrawler-qe3y5qgjgyceaazkpajrzd.streamlit.app/

**三个标签页：**

**单日查询**
- 选择日期，查询当日上交所/深交所的股票和基金成交额
- 同时显示亿元和万亿元两个单位
- 支持 CSV 下载
- 对节假日/周末给出友好提示

**批量查询**
- 选择日期范围，自动筛选交易日
- 使用 `ThreadPoolExecutor(max_workers=5)` 并行获取，带实时进度条
- 双表显示（亿元/万亿元）
- 支持 CSV 下载

**推送设置**
- 输入邮箱 → 添加 → 通过 GitHub Actions 发送验证邮件（含前一交易日数据）
- 已订阅邮箱列表，每行附带退订按钮
- 配置保存在 GitHub 仓库的 `config.json` 中

### 2. 定时推送（GitHub Actions）

- **触发时间：** 每天 1:00 UTC（北京时间 9:00），cron 表达式 `0 1 * * *`
- **逻辑：** 检查前一天是否为交易日 → 是则获取数据并发送给所有已订阅邮箱 → 记录 `last_sent_date` 防重复
- **非交易日：** 前一天不是交易日则直接跳过，不发邮件
- **发送邮箱：** QQ 邮箱（smtp.qq.com），465 端口 SSL / 587 端口 STARTTLS 双备选

### 3. 验证邮件

- **触发方式：** 网页端通过 GitHub API 的 `workflow_dispatch` 触发，POST 到 `/repos/{owner}/{repo}/actions/workflows/send_daily.yml/dispatches`
- **内容：** 与定时推送相同格式，含前一交易日完整数据
- **目的：** 新订阅者可立即确认邮箱是否能正常收到，无需等到次日早上

---

## 技术架构

```
用户浏览器
    │
    ▼
Streamlit Cloud ───→ 上交所 API (query.sse.com.cn)
    │                 深交所 API (www.szse.cn)
    │
    ├── GitHub API (读/写 config.json)
    │
    └── GitHub API (触发 workflow_dispatch)
            │
            ▼
    GitHub Actions ──→ 上交所/深交所 API
            │          SMTP → QQ邮箱 → 收件人
            │
            └── 每天 cron 触发 (1:00 UTC)
```

### 数据流

1. **查询时（同步）：** Web 页直接向 SSE/SZSE API 发送 HTTP 请求，解析后展示
2. **推送时（异步）：** GitHub Actions 先 `git pull` 拉取 config.json → 获取 API 数据 → SMTP 发送
3. **验证时（异步）：** Web 页触发 GitHub Actions → 同上流程

---

## 数据源详情

### 上交所（SSE）

- **接口：** `https://query.sse.com.cn/commonQuery.do`
- **方法：** GET
- **参数：**
  - `sqlId`: `COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C`（固定）
  - `type`: `inParams`（固定）
  - `SEARCH_DATE`: `YYYY-MM-DD`
  - `PRODUCT_CODE`: `17`（股票）/ `05`（基金）
- **请求头：** 必须设置 `Referer: https://www.sse.com.cn/`
- **响应：** JSON，路径 `result[0].TRADE_AMT`，单位：亿元
- **注意事项：** 海外访问正常，无需特殊网络

### 深交所（SZSE）

- **接口：** `https://www.szse.cn/api/report/ShowReport`
- **方法：** GET
- **参数：**
  - `SHOWTYPE`: `xlsx`（固定）
  - `CATALOGID`: `1803_sczm`（固定）
  - `TABKEY`: `tab1`（固定）
  - `txtQueryDate`: `YYYY-MM-DD`
  - `random`: 随机数（防缓存，实际作用有限）
- **请求头：** 必须设置 `Referer: https://www.szse.cn/market/overview/index.html`
- **响应：** Excel 文件（.xlsx），需用 `openpyxl` 解析
- **解析方式：** 读取"证券类别"列，匹配"股票"/"基金"，取对应行第三列的成交金额（元），除以 1e8 转为亿元
- **注意事项：** 海外访问有时不稳定，配置了 HTTPS 和 HTTP 双地址备选

### 交易日判断

- 使用 `chinese_calendar` 库的 `is_workday()` 方法
- 自动覆盖：周末、法定节假日、调休上班日
- 无需手动维护节假日列表

---

## 快速开始（本地开发）

### 前置条件

- Python 3.10+
- 一个 QQ 邮箱（用于 SMTP 发信）
- GitHub 账号（可选，用于测试 Actions）

### 1. 克隆仓库

```bash
git clone https://github.com/Weifeng-zhong/stock_crawler.git
cd stock_crawler/stock_tool
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 测试数据获取

```python
python -c "
from daily_fetch import fetch_sse_stock, fetch_sse_fund, fetch_szse
ss = fetch_sse_stock('2026-07-16')
sf = fetch_sse_fund('2026-07-16')
zs, zf = fetch_szse('2026-07-16')
print(f'SSE股票: {ss}, SSE基金: {sf}, SZSE股票: {zs}, SZSE基金: {zf}')
"
```

### 4. 测试邮件发送

```bash
# Windows PowerShell
$env:MAIL_USER="your_email@qq.com"
$env:MAIL_PASS="your_smtp_code"
python daily_fetch.py --verify-email "test@example.com"
```

### 5. 运行网页（本地）

```bash
streamlit run app.py
```

---

## 部署指南

### Streamlit Cloud 部署

1. Fork/Clone 到 GitHub 仓库
2. 登录 https://streamlit.io/cloud
3. 新建 App → 选择仓库 → 分支 `master` → 入口 `stock_tool/app.py` → Deploy
4. 在 Settings → Secrets 中添加：

```
GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxx"
```

### GitHub Actions 部署

代码推送到仓库后自动生效，无需额外部署步骤。

---

## GitHub Secrets 配置

前往：`仓库 → Settings → Secrets and variables → Actions`

| Secret | 值 | 说明 |
|--------|---|------|
| `MAIL_USER` | `your_email@qq.com` | 发件邮箱地址 |
| `MAIL_PASS` | `xxxxxxxxxxxxxxxx` | QQ 邮箱 SMTP 授权码（非登录密码） |

### QQ 邮箱 SMTP 授权码获取方式

1. 登录 [mail.qq.com](https://mail.qq.com/)
2. 设置 → 账户 → POP3/SMTP服务 → 开启
3. 按指引发送短信，生成授权码（16位字母）
4. 复制到 GitHub Secrets 的 `MAIL_PASS`

### 授权码过期处理

如果发现 SMTP 登录失败（550/535 错误），重新生成授权码并更新 GitHub Secrets 即可。

---

## GitHub Actions 工作流

### 工作流文件

`.github/workflows/send_daily.yml`

### 触发器

| 事件 | 说明 |
|------|------|
| `schedule: 0 1 * * *` | 每天 1:00 UTC（9:00 BJT）自动运行 |
| `workflow_dispatch` | 手动触发，支持传入 `verify_email` 参数 |

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `verify_email` | string | 否 | 指定一个邮箱发送验证邮件，不填则按 config.json 群发 |

### 执行流程

```
1. actions/checkout@v4          ← 拉取代码
2. actions/setup-python@v5      ← 安装 Python 3.12
3. pip install -r requirements.txt  ← 安装依赖
4. python daily_fetch.py ...     ← 执行主逻辑
```

### 查看运行日志

1. 打开 https://github.com/Weifeng-zhong/stock_crawler/actions
2. 点击对应 workflow run
3. 点击 `fetch-and-send` job
4. 展开 `获取数据并发送邮件` step

---

## 依赖清单

| 包 | 版本约束 | 用途 |
|---|---------|------|
| `streamlit` | < 2 | Web UI 框架 |
| `requests` | 最新 | HTTP 请求 |
| `pandas` | < 3.0 | 数据分析、Excel 解析；3.0+ 有 segfault 风险 |
| `openpyxl` | < 3.2 | Excel 读写；3.2+ 存在不兼容变更 |
| `chinese_calendar` | 最新 | 中国节假日判断 |

### pandas 版本说明

**不要将 pandas 升级到 3.0+。** 经测试，pandas 3.0.3 + openpyxl 3.2.x 在读取 SZSE 的 Excel 文件时会触发 Segmentation Fault（段错误），导致应用崩溃。详见 `requirements.txt` 中的 `<3.0` 约束。

---

## 常见问题

### Q: 邮件收不到？

1. 确认 GitHub Secrets 中的 `MAIL_PASS` 是否为最新授权码
2. 检查 GitHub Actions 运行日志是否有错误
3. 检查垃圾箱
4. 验证邮件通过 `workflow_dispatch` 发送，需等待 1-2 分钟

### Q: 深交所数据为 "-" 但上交所正常？

深交所海外访问不稳定，系统已配置双地址重试。如果持续失败，检查 `www.szse.cn` 是否可访问。

### Q: 网页打不开（一直加载）？

Streamlit Cloud 免费版在闲置 15 分钟后会休眠，刷新页面等待 10-20 秒即可唤醒。

### Q: 如何添加新邮箱？

网页 → 推送设置 → 输入邮箱 → 点添加 → 等待验证邮件。

### Q: 如何退订？

网页 → 推送设置 → 已订阅邮箱列表 → 点退订。

---

## 扩展指南

### 新增数据维度

如果要增加新的数据指标（如北向资金、两融余额）：

1. 在 `daily_fetch.py` 中新增获取函数（如 `fetch_northbound(date_str)`）
2. 在 `app.py` 中调用该函数并展示
3. 在 `daily_fetch.py` 的 `fetch_send()` 中拼入邮件内容
4. 邮件正文格式需同步调整

### 更换 SMTP 发信商

如需更换为其他邮箱：

1. 修改 `daily_fetch.py` 中 `send_email()` 的 SMTP 服务器地址和端口
2. 更新 GitHub Secrets 中的 `MAIL_USER` / `MAIL_PASS`

常见 SMTP 配置：

| 服务商 | 服务器 | SSL 端口 | STARTTLS 端口 |
|--------|--------|---------|-------------|
| QQ 邮箱 | smtp.qq.com | 465 | 587 |
| 163 邮箱 | smtp.163.com | 465 | 587 |
| Gmail | smtp.gmail.com | 465 | 587 |
| Outlook | smtp.office365.com | 465 | 587 |

### 修改推送时间

在 `.github/workflows/send_daily.yml` 中修改 cron 表达式。注意是 UTC 时间。

### 修改邮件格式

在 `daily_fetch.py` 的 `fetch_send()` 函数中修改 `subject` 和 `body` 变量。

### 新增数据源

如果新增的交易所或数据源返回格式不同（如 CSV、XML）：

1. 参考 `fetch_szse()` 的 try/except 模式编写新的获取函数
2. 确保函数返回 `(stock_value, fund_value)` 格式或按需调整
3. 更新类型定义和文档

---

## 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-10 | 1.0 | 初始版本，基于 Playwright 的爬虫 |
| 2026-07-11 | 2.0 | 改为直接调用 SSE/SZSE API，移除 Playwright |
| 2026-07-12 | 2.1 | Streamlit 网页上线，支持单日/批量查询 |
| 2026-07-13 | 2.2 | 邮件推送功能上线，GitHub Actions 定时任务 |
| 2026-07-14 | 2.3 | 多邮箱订阅/退订，验证邮件 |
| 2026-07-15 | 2.4 | SMTP 从 163 切换到 QQ 邮箱 |
| 2026-07-17 | 2.5 | 使用 chinese_calendar 替代硬编码节假日 |

---

## 联系

- 项目维护：Weifeng Zhong
- GitHub：https://github.com/Weifeng-zhong/stock_crawler
- 在线演示：https://stockcrawler-qe3y5qgjgyceaazkpajrzd.streamlit.app/
