# DDL 急救站 · Windows 本地部署

本地运行不依赖云端排队，数据保存在自己的电脑。

## 1. 下载部署包

打开 GitHub 仓库：

```text
https://github.com/DZQingya/ddl-rescue-cloud
```

点击 `Code → Download ZIP`，解压到 D 盘目录。

## 2. 安装 Python

安装 Python 3.12 或更新版本，安装时勾选：

```text
Add Python to PATH
```

## 3. 启动

在解压目录打开 PowerShell：

```powershell
python -m pip install -r requirements.txt
python -m streamlit run work\app.py
```

浏览器打开：

```text
http://localhost:8501
```

## 4. 手机在同一 Wi-Fi 使用

```powershell
python -m streamlit run work\app.py --server.address 0.0.0.0 --server.port 8501
```

手机打开：

```text
http://电脑局域网IP:8501
```

## 说明

- 默认使用 mock 解析，不需要 API Key；
- 使用真实模型时在 PowerShell 设置 `DDL_LLM_MODE=real` 等环境变量；
- 本地 SQLite 数据在自己的电脑上，不经过云端；
- 云端和本地是两个独立环境，数据不会自动同步。
