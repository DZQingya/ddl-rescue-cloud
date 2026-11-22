# DDL 急救站 v0.7-guided 云部署包

本版采用三步向导：粘贴通知 → 生成计划 → 今天做。

# DDL 急救站 · 云部署包

目标：把 `v0.6.2-final-r2` 部署到公网，让 iPhone 直接用 Safari 打开，不再依赖你电脑上的 Streamlit 进程。

> 部署后，日常使用只需要手机；部署本身仍需要一次性登录 GitHub 和云平台。

## 方式一：Streamlit Community Cloud（推荐，最快）

### 1. 上传到 GitHub

新建一个 GitHub 仓库，把本目录**里面的内容**上传到仓库根目录：

```text
requirements.txt
Procfile
work/
data/
.streamlit/
```

不要上传整个外层文件夹再套一层。

### 2. 创建 Streamlit App

打开：

```text
https://share.streamlit.io
```

选择：

- Repository：刚创建的仓库
- Branch：`main`
- Main file path：`work/app.py`
- Python version：优先选 3.12

点击 Deploy。

### 3. 手机使用

部署完成后会得到一个公网 URL。iPhone Safari 打开该 URL，再点：

```text
分享 → 添加到主屏幕
```

之后可以从桌面图标进入，不需要电脑一直开机。

## 方式二：Render / Railway

本包带有：

- 根目录 `requirements.txt`
- `Procfile`

平台启动命令：

```bash
streamlit run work/app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true
```

健康检查路径：

```text
/_stcore/health
```

## 当前部署的边界

1. 默认使用 mock 解析，可完整演示产品流程；
2. 真实模型需要云平台环境变量：
   - `DDL_LLM_MODE=real`
   - `DDL_LLM_BASE_URL`
   - `DDL_LLM_API_KEY`
   - `DDL_LLM_MODEL`
3. API Key 不要写进 GitHub、代码或 README；
4. 当前 SQLite 数据库适合单人演示。云实例重启后数据可能重置；
5. 多用户正式产品必须换 PostgreSQL 等持久化数据库，并加登录和隔离；
6. 不要把真实聊天记录、手机号、学号等隐私数据放进公共演示环境。

## 验收

1. 电脑先本地启动一次，确认页面正常；
2. 云部署成功后，用手机流量关闭 Wi-Fi 访问，确认不依赖局域网；
3. 测试一条多 DDL 通知；
4. 完成一个 DDL，确认另一个变今日主攻；
5. 卡住并重新生成计划；
6. 删除二次确认；
7. 添加入口和页面在手机上没有横向溢出。

## 对外口径

> 手机端可通过云端响应式网页独立访问，不依赖用户电脑常开。当前不是原生 iOS App，原生安装包仍未交付。
