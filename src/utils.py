import smtplib
import subprocess
import os
import logging
from email.mime.text import MIMEText
from passlib.context import CryptContext
import string
import random

logging.basicConfig(filename='account_management.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_username_from_email(email: str) -> str:
    return 'p' + email.split('@')[0]

def user_exists(username):
    try:
        subprocess.run(["id", username], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def create_server_account(email: str, public_key: str | None) -> str:
    username = get_username_from_email(email)
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    
    # 如果不存在
    if not user_exists(username):
        subprocess.run(['useradd', '-m', '-s', '/bin/bash', username], check=True)
        subprocess.run(['bash', '-c', f'echo "{username}:{password}" | chpasswd'], check=True)
        logging.info(f"已为 {email} 创建服务器账户")
    else:
        subprocess.run(['usermod', '-U', username], check=True)
        subprocess.run(['usermod', '-s', '/bin/bash', username], check=True)
        logging.info(f"已解锁 {email} 的服务器账户")
        password = "未修改"
    
    if public_key:
        home_dir = f"/home/{username}"
        ssh_dir = f"{home_dir}/.ssh"
        subprocess.run(['mkdir', '-p', ssh_dir], check=True)
        with open(f"{ssh_dir}/authorized_keys", 'w') as f:
            f.write(public_key)
            f.write('\n')
        subprocess.run(['chown', '-R', f"{username}:{username}", ssh_dir], check=True)
        subprocess.run(['chmod', '700', ssh_dir], check=True)
        subprocess.run(['chmod', '600', f"{ssh_dir}/authorized_keys"], check=True)
    
    return password

def ban_server_account(email: str):
    username = get_username_from_email(email)
    try:
        subprocess.run(['usermod', '-L', username], check=True)
        subprocess.run(['usermod', '-s', '/sbin/nologin', username], check=True)
        logging.info(f"已禁用 {email} 的服务器账户")
    except subprocess.CalledProcessError as e:
        logging.error(f"禁用 {email} 的服务器账户失败: {str(e)}")
        raise

def send_email(email: str, subject: str, content: str):
    msg = MIMEText(content)
    msg['Subject'] = subject
    msg["From"] = os.getenv('SMTP_USER')
    msg["To"] = email
    logging.info(f"发送邮件：\n收件人: {email}\n主题: {subject}\n正文: {content}")
    if os.getenv('SMTP_PASSWORD') == 'your-smtp-password':
        logging.info("SMTP 未设置，跳过发送邮件")
        return
    try:
        with smtplib.SMTP(os.getenv('SMTP_HOST'), os.getenv('SMTP_PORT')) as server:
            server.starttls()
            server.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
            server.send_message(msg)
            logging.info(f"已发送邮件至 {email}")
    except Exception as e:
        logging.error(f"发送邮件至 {email} 失败: {str(e)}")
        raise

def send_verification_email(email: str, code: str):
    uri = os.getenv('WEBSITE_URL')
    if uri is None:
        uri = f"http://{os.getenv('HOST')}:{os.getenv('PORT')}"
    else:
        uri = uri.rstrip('/')
    send_email(email, f'[{os.getenv("APP_TITLE")}] 验证您的邮箱', f"您的验证代码是：{code}\n请点击以下链接验证：{uri}/verify/{code}")

def send_rejection_email(email: str):
    send_email(email, f'[{os.getenv("APP_TITLE")}] 账户创建失败', "您的账户创建请求已被拒绝，你可以重新申请或者联系管理员。")

def send_account_details(email: str, password: str):
    send_email(email, f'[{os.getenv("APP_TITLE")}] 账号创建成功', f"您的账户已创建！\n用户名: {get_username_from_email(email)}\n密码: {password}")