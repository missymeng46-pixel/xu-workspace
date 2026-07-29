# 序 XU · 本地优先的个人工作台

一个运行在自己电脑上的个人工作空间，把任务计划、项目、内容、财务、运动打卡、收件箱和每日总结小票放在同一处。

数据默认保存在本机 SQLite 数据库中，不需要注册账号；DeepSeek 只用于可选的收件箱智能分类，不配置 API Key 也能正常使用核心功能。

## 功能

- 今日焦点：当天任务、完成状态和每日总结小票
- 计划：已逾期、今天、明天、未来 7 天、更晚与已完成
- 财务：收入、支出、月度预算、预算余额、分类统计和 CSV 导入
- 项目：待开始、进行中、待确认看板
- 内容：灵感池、制作中、待发布、已发布
- 运动：每日打卡、运动内容、时长、连续天数和月历
- 收件箱：DeepSeek 自动分类或完全离线的手动整理
- 手机联动：同一 Wi-Fi 下通过临时访问码访问同一份数据
- 本地优先：单用户 SQLite，无云端账号依赖

## 快速开始

需要 macOS 和 Python 3。

### 方式一：双击启动

1. 下载并解压项目。
2. 按住 `Control` 点击 `启动序.command`，选择“打开”。
3. 浏览器会自动打开 `http://127.0.0.1:4173/`。
4. 启动终端需要保持运行；关闭终端会停止本地服务。

如果 macOS 拦截脚本，请参考 `Apple无法验证时请看这里.txt`。

### 方式二：终端启动

```bash
git clone https://github.com/missymeng46-pixel/xu-workspace.git
cd xu-workspace
python3 server.py --host 0.0.0.0 --port 4173
```

然后访问：

```text
http://127.0.0.1:4173/
```

首次启动会自动创建 `data/xu.sqlite3`。

## 可选：启用 DeepSeek 分类

复制环境变量示例：

```bash
cp .env.example .env
```

在 `.env` 中填写自己的密钥：

```dotenv
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

也可以在 macOS 上运行 `配置DeepSeek.command`。`.env` 已被 Git 忽略，不要提交或发送自己的 API Key。

## 手机访问

1. Mac 与手机连接同一个可信 Wi-Fi。
2. 保持 Mac 和工作台服务运行。
3. 在电脑端点击“手机联动”，显示二维码和临时访问码。
4. 手机使用 Safari 打开地址并输入 6 位访问码。

如果使用 Shadowrocket、Clash 等 VPN/代理，请开启“允许局域网”或让 `192.168.0.0/16` 走 `DIRECT`。公共 Wi-Fi、访客 Wi-Fi和开启客户端隔离的路由器可能无法使用局域网访问。

## 数据与隐私

- 工作数据：`data/xu.sqlite3`
- DeepSeek 配置：`.env`
- 数据不会由本项目自动上传到第三方
- 只有使用 AI 分类时，当前收件箱文本才会发送到你配置的 DeepSeek 接口
- 手机访问使用每次启动生成的临时访问码和会话 Cookie

备份或迁移时，请复制整个 `data` 文件夹。公开反馈问题时，不要上传数据库、`.env`、访问码或包含个人信息的截图。

## CSV 格式

财务导入需要以下表头：

```csv
日期,类型,金额,分类,账户,项目,对方,备注
```

日期格式示例：`2026-07-29`；类型填写“收入”或“支出”。

## 技术栈

- 原生 HTML / CSS / JavaScript
- Python 标准库 HTTP Server
- SQLite
- qrcode.js

项目不依赖 Node.js 构建流程，适合直接下载和本地运行。

## 安全说明

本项目目前是本地单用户工具，不适合直接暴露到公网。`--host 0.0.0.0` 仅用于可信局域网内的手机访问。请不要做端口映射，也不要把局域网临时访问码当作公网身份认证方案。

安全问题请参考 `SECURITY.md`。

## 许可证

代码采用 [MIT License](LICENSE)。插画和第三方资源的许可范围请查看 [ASSETS.md](ASSETS.md) 及 `assets/vendor` 中的许可证文件。

