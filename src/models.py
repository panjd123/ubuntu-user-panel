from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from src.database import Base
import datetime
from dotenv import load_dotenv
import os

load_dotenv()

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    status = Column(String, default='未创建')  # 未创建, 活跃状态, 不活跃状态
    latest_approval_time = Column(DateTime, nullable=True)
    server_password = Column(String, nullable=True)
    applications = relationship("Application", back_populates="account")

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    public_key = Column(Text, nullable=True)
    application_reason = Column(Text, nullable=True)
    verification_code = Column(String, nullable=True)
    status = Column(String, default='等待验证')  # 等待验证, 等待管理员同意, 同意, 拒绝
    is_first_application = Column(Boolean, default=False)
    application_time = Column(DateTime, default=datetime.datetime.utcnow)
    account = relationship("Account", back_populates="applications")

class Whitelist(Base):
    __tablename__ = "whitelist"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    auto_approve = Column(Boolean, default=False)
    account_expiry_days = Column(Integer, default=365)
    homepage_message = Column(Text, default=os.getenv("HOMEPAGE_MESSAGE", "欢迎使用本系统！"))