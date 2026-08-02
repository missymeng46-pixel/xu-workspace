# 序 XU · 本地优先的个人工作台

一个运行在自己电脑上的个人工作空间，把任务计划、项目、内容、审美收藏、Vibe Coding 发现、财务、运动打卡、收件箱和每日总结小票放在同一处。

数据默认保存在本机 SQLite 数据库中，不需要注册账号；DeepSeek 只用于可选的收件箱智能分类，不配置 API Key 也能正常使用核心功能。

## 功能

- 今日焦点：当天任务、完成状态和每日总结小票
- 计划：已逾期、今天、明天、未来 7 天、更晚与已完成
- 财务：收入、支出、总预算与分类预算、分类折叠流水、预算余额、统计和 CSV 导入
- 项目：待开始、进行中、待确认和已完成四阶段看板
- 内容：灵感池、制作中、待发布、已发布
- 审美收藏：按配色、首页、字体排版、图表、3D、动画和直觉喜欢分类保存视觉灵感；支持选择、拖入和 `Command + V` 粘贴本地图片
- AI 审美画像：从收藏分类、标题和喜欢理由中持续总结个人偏好，每新增 3 条自动更新，也可手动刷新
- Vibe 雷达：聚合全球当天与最近 7 天的新项目、文章和开发者讨论，提供中文一句话概括与热点榜
- 运动：每日打卡、运动内容、时长、连续天数和月历
- 收件箱：DeepSeek 自动分类或完全离线的手动整理
- 微信入口：公众号文字消息进入收件箱，可由本机 Codex 后台理解整理
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

## Vibe 雷达

Vibe 雷达进入页面时按需加载，不会拖慢工作台首页。当前聚合 GitHub Search、Hacker News Algolia 和 Google News RSS 三个公开来源，不需要额外 API Key。热点榜综合项目 Star、社区讨论热度和发布时间排序；配置 DeepSeek 后生成高质量中文一句话概括，没有配置时显示基础中文说明。

- “今日发现”只计算发布时间明确属于今天的内容
- 其余结果会如实标注为“几小时前”或“几天前”
- 默认缓存 30 分钟，手动重新扫描有 60 秒保护
- 网络暂时不可用时优先回退到上一次成功结果
- 外部内容可一键保存到工作台的内容灵感池

外部内容和链接仅用于发现与跳转，版权归原作者及来源网站所有。

## 审美收藏与 AI 画像

添加收藏时，可以点击上传区选择图片、把图片拖进去，或先复制图片，再在弹窗打开时按 `Command + V`。支持 JPG、PNG、WebP 和 GIF，单张最大 8 MB。图片保存在本机 `data/aesthetic_uploads`，不会因为收藏操作自动上传到第三方。

本版审美画像不分析图片像素，只根据你选择的文件夹、收藏标题、“为什么喜欢”和来源域名学习。配置 DeepSeek 后，这些文字信息会发送到你配置的 DeepSeek 接口，生成更细致的画像；图片文件不会发送。未配置 DeepSeek 时仍会显示本地基础画像。

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

## 可选：接入微信消息

此功能使用微信官方公众号回调，不读取个人微信聊天，也不依赖非官方微信 Hook。

1. 登录[微信公众平台测试号](https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login)，关注测试号并取得自己的 OpenID。
2. 在接口配置信息中自定义一个 Token。
3. 双击 `配置微信接入.command`，填写同一个 Token 和允许写入的 OpenID。
4. 重新启动工作台，再双击 `启动微信中转.command`。
5. 在中转终端复制 `https://...trycloudflare.com` 地址；把 `https://...trycloudflare.com/api/wechat/callback` 填入测试号接口 URL，选择明文模式并提交。
6. 给测试号发送文字，消息会进入工作台收件箱，再由本机 Codex 后台理解为任务、财务、内容、项目或笔记。

这不是把微信接进某个正在打开的 Codex 对话，而是每条微信文字触发一次独立的 `codex exec` 临时任务。使用前需要本机安装并登录 Codex CLI。Codex 在只读空目录中运行，插件、MCP 和 Shell 工具均关闭，只能返回符合 `codex-wechat-schema.json` 的整理结果。

安全机制还包括微信 SHA-1 签名校验、OpenID 白名单、消息 ID 去重、1000 字长度限制和 Codex 串行调用。Cloudflare Quick Tunnel 地址每次启动可能变化，仅适合个人测试；长期运行请使用固定域名和持久 Tunnel。

## 数据与隐私

- 工作数据：`data/xu.sqlite3`
- DeepSeek 配置：`.env`
- 微信 Token 与 OpenID 白名单：`.env`
- 数据不会由本项目自动上传到第三方
- 使用 AI 收件箱分类时，当前收件箱文本会发送到你配置的 DeepSeek 接口
- 使用 AI 审美画像时，收藏标题、文件夹、喜欢理由和来源域名会发送到 DeepSeek；收藏图片不会发送
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
