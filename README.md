# Ubuntu-User-Panel

## 功能

- [x] 账号申请
- [x] 账号发放
- [ ] 账号管理
- [ ] 账号删除

## 快速开始

```bash
# 他需要以 root 用户身份运行，请注意安全问题

# 确保你已经安装了 Python
apt update && apt install python3 python3-pip python3-venv

# uv
curl -LsSf https://astral.sh/uv/install.sh | bash
uv venv
uv pip install -e .

# pip
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 启动服务
uv run python -m src.main
```
