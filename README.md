# 沪深交易所日成交数据系统

自动获取上海证券交易所和深圳证券交易所每日成交额（股票 + 基金），提供 Web 查询、批量追溯、定时邮件推送功能。数据有双重来源保障（官方 API + 行情兜底），邮件推送具备防空数据机制。

---

## 目录

- [项目结构](#项目结构)
- [功能概述](#功能概述)
- [技术架构](#技术架构)
- [数据源与兜底机制](#数据源与兜底机制)
- [快速开始（本地开发）](#快速开始本地开发)
- [部署指南](#部署指南)
- [Secrets 配置](#secrets-配置)
- [GitHub Actions 工作流](#github-actions-工作流)
- [依赖清单](#依赖清单)
- [常见问题](#常见问题)
- [扩展指南](#扩展指南)
- [版本历史](#版本历史)

---

## 项目结构

```
仓库根目录/
├── app.py                 # Streamlit 网页应用（入口）
├── daily_fetch.py         # 定时推送 + 验证邮件脚本（GitHub Actions 运行）
├── stock_api.py           # 公共数据层：SSE/SZSE 获取 + 兜底 + 交易日判断
├── config.json            # 订阅配置（网页端写入，Actions 读取）
├── requirements.txt       # Python 依赖
├── .gitignore             # 排除 secrets/缓存文件
├── .github/workflows/
│   └── send_daily.yml     # GitHub Actions 定时任务
└── README.md              # 本文件
```

### 文件职责

| 文件 | 运行环境 | 职责 |
|------|---------|------|
| `app.py` | Streamlit Cloud | Web UI：单日/批量查询、订阅管理 |
| `daily_fetch.py` | GitHub Actions | 获取数据 + SMTP 发邮件（定时/验证） |
| `stock_api.py` | 两者 | 数据获取统一入口：官方接口 + 腾讯兜底 + 深交所解析 |
| `send_daily.yml` | GitHub Actions | 定时触发（cron）+ 手动触发（workflow_dispatch） |
| `config.json` | GitHub 仓库 | 订阅邮箱列表、最后发送日期 |
| `requirements.txt` | 两者 | 锁定依赖版本 |

---

## 功能概述

### 1. Web 查询（Streamlit Cloud）

**网址：** https://stockcrawler-qe3y5qgjgyceaazkpajrzd.streamlit.app/

**三个标签页：**

**单日查询**
- 选择日期，查询当日上交所/深交所的股票和基金成交额
- 同时显示亿元和万亿元两个单位，支持 CSV 下载
- 节假日/周末给出友好提示

**批量查询**
- 选择日期范围，自动筛选交易日（周末 + 法定节假日 + 调休）
- `ThreadPoolExecutor(max_workers=5)` 并行获取，带实时进度条
- 双表显示（亿元/万亿元），支持 CSV 下载

**推送设置**
- 输入邮箱（含格式校验）→ 添加 → 通过 GitHub Actions 发送验证邮件
- 已订阅邮箱列表，每行附带退订按钮
- 配置保存在 GitHub 仓库的 `config.json` 中

### 2. 定时推送（GitHub Actions）

- **触发时间：** 每天 1:00 UTC（北京时间 9:00），cron 表达式 `0 1 * * *`
- **逻辑：** 检查前一天是否为交易日 → 获取数据 → 群发订阅邮箱 → 记录 `last_sent_date` 防重复
- **发送邮箱：** QQ 邮箱（smtp.qq.com），465 端口 SSL / 587 端口 STARTTLS 双备选

### 3. 防空数据机制（重要）

| 场景 | 行为 |
|------|------|
| 单项数据获取失败 | 邮件该项显示 **"获取失败"**（非"-"），运行日志打印警告 |
| 全部数据获取失败 | **不发送邮件**，脚本退出码非 0（Actions 运行标红可见） |
| 部分收件人发送失败 | 不影响其他收件人，失败单独记录，整体退出码非 0 |

---

## 技术架构

```
用户浏览器
    │
    ▼
Streamlit Cloud ───→ 上交所官方 API (query.sse.com.cn) ──失败──→ 腾讯行情接口（兜底）
    │                 深交所官方 API (www.szse.cn)     ──失败──→ 深证综指（股票兜底）
    │
    ├── GitHub API (读/写 config.json)
    │
    └── GitHub API (触发 workflow_dispatch)
            │
            ▼
    GitHub Actions ──→ 数据获取（官方 + 兜底）→ SMTP → QQ邮箱 → 收件人
            │
            └── 每天 cron 触发 (1:00 UTC)
```

### 数据流

1. **查询时（同步）：** 网页直接请求数据接口（官方优先，失败自动降级兜底）
2. **推送时（异步）：** GitHub Actions 拉取代码 → 读取 config.json → 获取数据 → SMTP 群发
3. **验证时（异步）：** 网页触发 GitHub Actions → 向指定邮箱发送验证邮件（跳过防重逻辑）

---

## 数据源与兜底机制

### 上交所（SSE）

- **官方接口：** `https://query.sse.com.cn/commonQuery.do`
  - 参数：`sqlId=COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C`、`SEARCH_DATE=YYYY-MM-DD`、`PRODUCT_CODE=17`(股票)/`05`(基金)
  - 必须携带 `Referer: https://www.sse.com.cn/`
  - 响应：JSON，`result[0].TRADE_AMT`，单位亿元
  - **注意：** 该接口对部分海外 IP（如 GitHub Actions 服务器）存在间歇性拦截，属正常现象
- **兜底接口：** 腾讯 `web.ifzq.gtimg.cn/appstock/app/newfqkline/get`
  - 上证指数 `sh000001`（股票）、上证基金指数 `sh000011`（基金）
  - 成交额字段单位万元，÷10000 转为亿元
  - **精度：** 与官方差异 <0.2%（万亿单位两位小数显示无差别）

### 深交所（SZSE）

- **官方接口：** `https://www.szse.cn/api/report/ShowReport`
  - 参数：`SHOWTYPE=xlsx`、`CATALOGID=1803_sczm`、`TABKEY=tab1`、`txtQueryDate=YYYY-MM-DD`
  - 必须携带 `Referer: https://www.szse.cn/market/overview/index.html`
  - 响应：Excel 文件，openpyxl 解析"证券类别"列匹配"股票"/"基金"，金额 ÷1e8 转亿元
  - HTTPS/HTTP 双地址自动备选
- **兜底接口：** 腾讯深证综指 `sz399106`（仅股票，差异约 0.1%）
  - 深交所基金无可靠历史兜底源（深证基金指数已停更），失败时按"获取失败"标注

### 交易日判断

- `chinese_calendar` 库的 `is_workday()`，自动覆盖周末、法定节假日、调休上班日

---

## 快速开始（本地开发）

### 前置条件

- Python 3.10+
- QQ 邮箱（SMTP 发信用）
- GitHub 账号（可选）

### 1. 克隆仓库

```bash
git clone https://github.com/Weifeng-zhong/stock_crawler.git
cd stock_crawler
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 测试数据获取

```python
python -c "
from stock_api import fetch_sse_stock, fetch_sse_fund, fetch_szse
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

1. 推送到 GitHub 仓库
2. 登录 https://streamlit.io/cloud
3. 新建 App → 选择仓库 → 分支 `master` → 入口 `app.py` → Deploy
4. Settings → Secrets 中添加 `GITHUB_TOKEN`（用于网页端读写 config.json）

### GitHub Actions 部署

代码推送后自动生效，无需额外部署。

---

## Secrets 配置

前往：`仓库 → Settings → Secrets and variables → Actions`

| Secret | 值 | 说明 |
|--------|---|------|
| `MAIL_USER` | `your_email@qq.com` | 发件邮箱地址 |
| `MAIL_PASS` | `xxxxxxxxxxxxxxxx` | QQ 邮箱 SMTP 授权码（16 位，非登录密码） |

Streamlit Cloud Secrets 中另需：

| Secret | 说明 |
|--------|------|
| `GITHUB_TOKEN` | 网页端读写 config.json 和触发工作流（需要 repo + workflow 权限） |

### QQ 邮箱 SMTP 授权码获取

1. 登录 [mail.qq.com](https://mail.qq.com/)
2. 设置 → 账户 → POP3/SMTP服务 → 开启
3. 按指引生成授权码（16 位字母）
4. 填入 GitHub Secrets 的 `MAIL_PASS`
5. 若 SMTP 登录失败（550/535），重新生成授权码并更新

---

## GitHub Actions 工作流

### 触发器

| 事件 | 说明 |
|------|------|
| `schedule: 0 1 * * *` | 每天 1:00 UTC（9:00 BJT）自动运行 |
| `workflow_dispatch` | 手动触发，可传 `verify_email` 参数跳过防重直接发验证邮件 |

### 执行流程

```
1. actions/checkout@v4           ← 拉取代码
2. actions/setup-python@v5       ← 安装 Python 3.12
3. pip install -r requirements.txt
4. python daily_fetch.py          ← 定时：按 config.json 群发（防重）
   python daily_fetch.py --verify-email <邮箱>   ← 验证：强制发送指定邮箱
5. 定时模式成功后 git push 回写 last_sent_date
```

### 运行失败时的排查入口

1. 打开 https://github.com/Weifeng-zhong/stock_crawler/actions
2. 红色 ❌ 运行即表示发送失败或数据全失败（退出码非 0）
3. 展开 `获取数据并发送邮件` step，查看 `SSE 官方接口异常` / `SSE 使用腾讯兜底数据` / `警告: ...获取失败` 等日志

---

## 依赖清单

| 包 | 版本约束 | 用途 |
|---|---------|------|
| `streamlit` | < 2 | Web UI 框架 |
| `requests` | 最新 | HTTP 请求 |
| `pandas` | < 3.0 | Excel 解析；3.0+ 有 segfault 风险 |
| `openpyxl` | < 3.2 | Excel 读写；3.2+ 存在不兼容变更 |
| `chinese_calendar` | 最新 | 中国节假日判断 |

> **不要将 pandas 升级到 3.0+。** 经测试，pandas 3.0.3 + openpyxl 3.2.x 读取 SZSE Excel 会触发 Segmentation Fault。

---

## 常见问题

### Q: 邮件里某项显示"获取失败"？
系统已尽力获取（官方 + 兜底均失败），该项数据当天缺失。运行日志会打印警告，Actions 可查具体原因。次日自动恢复。

### Q: 邮件收不到？
1. 确认 GitHub Secrets 的 `MAIL_PASS` 是否为最新授权码
2. 检查 GitHub Actions 运行日志（红色 ❌ = 失败）
3. 检查垃圾箱；验证邮件约 1-2 分钟到账

### Q: 上交所数据为"获取失败"但深交所正常？
上交所官方接口对 GitHub Actions 的海外 IP 有间歇性拦截，系统会自动降级到腾讯行情兜底（数值差异 <0.2%），一般不会出现。

### Q: 网页打不开（一直加载）？
Streamlit Cloud 免费版闲置 15 分钟后休眠，唤醒/部署需 1-5 分钟，刷新等待即可。

### Q: 如何添加/退订邮箱？
网页 → 推送设置 → 添加（需合法邮箱格式）/ 退订按钮。

---

## 扩展指南

### 新增数据维度

1. 在 `stock_api.py` 中新增获取函数（如 `fetch_northbound(date_str)`）
2. 在 `app.py` 中调用并展示
3. 在 `daily_fetch.py` 的 `fetch_send()` 中拼入邮件内容（失败项自动标注）

### 更换 SMTP 发信商

1. 修改 `daily_fetch.py` 中 `send_email()` 的 SMTP 服务器和端口
2. 更新 GitHub Secrets 的 `MAIL_USER` / `MAIL_PASS`

常见 SMTP：QQ `smtp.qq.com`(465/587)、163 `smtp.163.com`(465/587)、Gmail `smtp.gmail.com`(465/587)

### 修改推送时间

修改 `.github/workflows/send_daily.yml` 的 cron 表达式（UTC 时间）。

### 修改邮件格式

修改 `daily_fetch.py` 的 `fetch_send()` 中 `subject` 和 `body`。

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
| 2026-08-06 | 2.6 | 上交所加腾讯兜底 + 失败日志；修复 SMTP 日志文案、死代码；深交所失败日志 |
| 2026-08-06 | 2.7 | 提取公共模块 stock_api.py；深交所股票兜底；防空数据机制（获取失败标注/全失败不发送/收件人容错）；邮箱格式校验；批量查询过滤节假日；.gitignore；secrets 崩溃修复 |

---

## 联系

- 项目维护：Weifeng Zhong
- GitHub：https://github.com/Weifeng-zhong/stock_crawler
- 在线演示：https://stockcrawler-qe3y5qgjgyceaazkpajrzd.streamlit.app/
