# DDL 急救站 · Windows 一键本地部署

## 一键部署

1. 打开 GitHub 仓库：
   `https://github.com/DZQingya/ddl-rescue-cloud`
2. 点击 `Code → Download ZIP`
3. 解压 ZIP
4. 双击根目录的 `一键部署.bat`

脚本会自动：

- 查找 Python；
- 如果系统有 winget 且没有 Python，自动安装 Python 3.12；
- 创建 `.venv`；
- 安装依赖；
- 启动 Streamlit；
- 自动打开 `http://localhost:8501`。

首次运行需要联网安装依赖，之后会复用本地环境。

## 手机访问

部署完成后，手机和电脑连接同一 Wi-Fi，打开：

```text
http://电脑局域网IP:8501
```

Windows 防火墙弹窗时，请允许 Python 在专用网络通信。

## 手动启动（可选）

如果一键脚本失败，在解压目录打开 PowerShell：

```powershell
python -m pip install -r requirements.txt
python -m streamlit run work\app.py --server.address 0.0.0.0 --server.port 8501
```

## 说明

- 默认 mock 解析，不需要 API Key；
- 本地 SQLite 数据保存在自己的电脑；
- 云端和本地数据不会自动同步；
- 真实模型配置通过 PowerShell 环境变量设置。
