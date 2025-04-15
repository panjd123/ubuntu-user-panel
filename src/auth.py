from fastapi import Depends, HTTPException, status, Request
import os

def get_current_user(request: Request):
    token = request.cookies.get("auth_token")
    if not token or token != os.getenv("AUTH_TOKEN", "admin123"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"user": "admin"}

def authenticate_admin_password(password: str) -> bool:
    valid_passwords = os.getenv("ADMIN_PASSWORDS", "admin123").split(",")
    return password in valid_passwords

def authenticate_user(email: str, db: Depends) -> bool:
    from src.models import Account
    account = db.query(Account).filter(Account.email == email).first()
    return account is not None