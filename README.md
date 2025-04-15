# Ubuntu-User-Panel

## 功能

- [x] 账号申请
- [x] 账号发放
- [] 账号管理
- [] 账号删除

## 快速开始

```bash
# 确保你已经安装了 Python
sudo apt install python3 python3-pip python3-venv

# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | bash

# 创建虚拟环境
uv venv
uv pip install -e .

# 启动服务
uv run python -m src.main
```