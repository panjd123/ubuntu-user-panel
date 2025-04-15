from fastapi import FastAPI, Depends, HTTPException, status, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from src.database import SessionLocal, init_db
from src.models import Account, Application, Whitelist, Settings
from src.utils import send_verification_email, create_server_account, send_account_details, ban_server_account, send_rejection_email
from src.auth import get_current_user, authenticate_admin_password, authenticate_user
from pydantic import EmailStr
import os
import datetime
import logging
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from sqlalchemy import func, desc

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        # logging.info("启动过期账户检查任务...")
        # asyncio.create_task(check_expired_accounts())
    except Exception as e:
        logging.error(f"启动失败: {str(e)}")
        raise
    yield
    logging.info("应用正在关闭。")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

logging.basicConfig(filename='account_management.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": os.getenv("APP_TITLE", "服务器账户申请"),
        "application_reason_placeholder": "1.您的姓名、学号、专业、班级等信息\n2.申请的课程和理由\n3.是否了解服务器使用规范，并能承担相应安全责任",
        "homepage_message": settings.homepage_message
    })

def valid_email(email: str) -> bool:
    domains = os.getenv("ALLOWED_EMAIL_DOMAINS", "").split(",")
    if len(domains) == 0 and domains[0] == "":
        return True
    return any(email.endswith(domain) for domain in domains)

@app.post("/apply", response_class=HTMLResponse)
async def apply_account(
    request: Request,
    email: EmailStr = Form(...),
    public_key: str = Form(None),
    application_reason: str = Form(...),
    db: Session = Depends(get_db)
):
    if not valid_email(email):
            raise HTTPException(status_code=400, detail="无效的邮箱域名")

    account = db.query(Account).filter(Account.email == email).first()
    if not account:
        account = Account(email=email, status='未创建')
        db.add(account)
        db.commit()

    verification_code = os.urandom(16).hex()
    application = Application(
        account_id=account.id,
        public_key=public_key,
        application_reason=application_reason,
        verification_code=verification_code,
        status='等待验证',
        is_first_application=(account.status == '未创建'),
        application_time=datetime.datetime.utcnow()
    )
    db.add(application)
    db.commit()

    send_verification_email(email, verification_code)
    return templates.TemplateResponse("message.html", {
        "request": request,
        "message": "已发送验证邮件，请检查您的邮箱。"
    })

@app.get("/verify/{code}", response_class=HTMLResponse)
async def verify_email(code: str, request: Request, db: Session = Depends(get_db)):
    application = db.query(Application).filter(Application.verification_code == code).first()
    if not application:
        raise HTTPException(status_code=404, detail="无效的验证代码")

    application.status = '等待管理员同意'
    application.verification_code = None
    db.commit()

    settings = db.query(Settings).first()
    if settings.auto_approve:
        try:
            account = db.query(Account).filter(Account.id == application.account_id).first()
            password = create_server_account(account.email, application.public_key)
            account.status = '活跃状态'
            account.latest_approval_time = datetime.datetime.utcnow()
            application.status = '同意'
            db.commit()
            send_account_details(account.email, password)
            logging.info(f"自动批准账户：{account.email}")
            return templates.TemplateResponse("message.html", {
                "request": request,
                "message": "账户已自动创建，请检查您的邮箱获取详细信息。"
            })
        except Exception as e:
            logging.error(f"自动批准失败：{account.email}: {str(e)}")
            application.status = '等待管理员同意'
            db.commit()

    return templates.TemplateResponse("message.html", {
        "request": request,
        "message": "邮箱已验证，等待管理员审批。"
    })

def get_latest_pendings(db: Session):
    subquery = ( 
        db.query( 
            Application.account_id, 
            func.max(Application.application_time).label('max_time') 
        ) 
        .group_by(Application.account_id)
        .subquery()
    )

    latest_pendings = ( 
        db.query(Application) 
        .join( 
            subquery, 
            (Application.account_id == subquery.c.account_id) 
            & (Application.application_time == subquery.c.max_time) 
            & (Application.status == '等待管理员同意')
        ) 
        .all() 
    )
    return latest_pendings

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    applications = db.query(Application).all()
    settings = db.query(Settings).first() # 使用子查询获取每个 account_id 的最大 application_time
    latest_pendings = get_latest_pendings(db)
    latest_pending_ids = {app.id for app in latest_pendings}
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "applications": applications,
        "latest_pending_ids": latest_pending_ids,
        "auto_approve": settings.auto_approve,
        "account_expiry_days": settings.account_expiry_days,
        "homepage_message": settings.homepage_message
    })

@app.post("/admin/approve/{application_id}", response_class=RedirectResponse)
async def approve_application(application_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="申请未找到")

    latest_application = db.query(Application).filter(Application.account_id == application.account_id).order_by(Application.application_time.desc()).first()
    if latest_application.id != application.id or application.status != '等待管理员同意':
        raise HTTPException(status_code=400, detail="只能批准最新的等待管理员同意的申请")

    try:
        account = db.query(Account).filter(Account.id == application.account_id).first()
        password = create_server_account(account.email, application.public_key)
        account.status = '活跃状态'
        account.latest_approval_time = datetime.datetime.utcnow()
        application.status = '同意'
        db.commit()
        send_account_details(account.email, password)
        logging.info(f"批准账户：{account.email}")
    except Exception as e:
        logging.error(f"批准失败：{account.email}: {str(e)}")
        raise HTTPException(status_code=500, detail="创建服务器账户失败")

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/reject/{application_id}", response_class=RedirectResponse)
async def reject_application(application_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="申请未找到")

    latest_application = db.query(Application).filter(Application.account_id == application.account_id).order_by(Application.application_time.desc()).first()
    if latest_application.id != application.id or application.status != '等待管理员同意':
        raise HTTPException(status_code=400, detail="只能拒绝最新的等待管理员同意的申请")

    application.status = '拒绝'
    db.commit()
    send_rejection_email(application.account.email)
    logging.info(f"拒绝账户：{application.account.email}")
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/toggle-auto-approve", response_class=RedirectResponse)
async def toggle_auto_approve(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(auto_approve=False)
        db.add(settings)

    settings.auto_approve = not settings.auto_approve
    db.commit()

    if settings.auto_approve:
        latest_pendings = get_latest_pendings(db)
        for application in latest_pendings:
            try:
                account = db.query(Account).filter(Account.id == application.account_id).first()
                password = create_server_account(account.email, application.public_key)
                account.status = '活跃状态'
                account.latest_approval_time = datetime.datetime.utcnow()
                application.status = '同意'
                send_account_details(account.email, password)
                logging.info(f"自动批准待处理的账户：{account.email}")
            except Exception as e:
                logging.error(f"自动批准失败：{account.email}: {str(e)}")
                continue
        db.commit()

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/set-expiry-days", response_class=RedirectResponse)
async def set_expiry_days(expiry_days: int = Form(...), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(account_expiry_days=365)
        db.add(settings)

    settings.account_expiry_days = expiry_days
    db.commit()
    logging.info(f"设置账户有效期为 {expiry_days} 天")
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/set-homepage-message", response_class=RedirectResponse)
async def set_homepage_message(message: str = Form(...), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(homepage_message="欢迎使用服务器账户申请系统。")
        db.add(settings)

    settings.homepage_message = message
    db.commit()
    logging.info("已更新首页消息")
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    try:
        current_user = get_current_user(request)
        if current_user:
            return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException:
        pass
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin/login", response_class=RedirectResponse)
async def admin_login(password: str = Form(...)):
    if authenticate_admin_password(password):
        response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="auth_token", value=os.getenv("AUTH_TOKEN", "admin123"), httponly=True)
        return response
    raise HTTPException(status_code=401, detail="密码错误")

@app.post("/admin/logout", response_class=RedirectResponse)
async def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("auth_token")
    return response

@app.get("/user/login", response_class=HTMLResponse)
async def user_login_page(request: Request):
    return templates.TemplateResponse("user_login.html", {"request": request})

@app.post("/user/login", response_class=RedirectResponse)
async def user_login(email: EmailStr = Form(...), db: Session = Depends(get_db)):
    if authenticate_user(email, db):
        response = RedirectResponse(url="/user", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="user_email", value=email, httponly=True)
        return response
    raise HTTPException(status_code=401, detail="邮箱未找到")

@app.get("/user", response_class=HTMLResponse)
async def user_dashboard(request: Request, db: Session = Depends(get_db)):
    email = request.cookies.get("user_email")
    if not email:
        return RedirectResponse(url="/user/login", status_code=status.HTTP_303_SEE_OTHER)
    
    account = db.query(Account).filter(Account.email == email).first()
    if not account:
        return RedirectResponse(url="/user/login", status_code=status.HTTP_303_SEE_OTHER)
    
    latest_application = db.query(Application).filter(Application.account_id == account.id).order_by(Application.application_time.desc()).first()
    return templates.TemplateResponse("user_dashboard.html", {
        "request": request,
        "email": email,
        "account": account,
        "latest_application": latest_application
    })
    
async def check_expired_accounts():
    while True:
        db = SessionLocal()
        try:
            now = datetime.datetime.utcnow()
            settings = db.query(Settings).first()
            expiry_days = settings.account_expiry_days
            expiry_threshold = now - datetime.timedelta(days=expiry_days)
            expired = db.query(Account).filter(
                Account.status == '活跃状态',
                Account.latest_approval_time < expiry_threshold
            ).all()
            for account in expired:
                try:
                    ban_server_account(account.email)
                    account.status = '不活跃状态'
                    logging.info(f"已禁用过期账户：{account.email}")
                except Exception as e:
                    logging.error(f"禁用过期账户 {account.email} 失败: {str(e)}")
            db.commit()
        finally:
            db.close()
        await asyncio.sleep(86400)

def main():
    import uvicorn
    uvicorn.run("src.main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8000)))
    
if __name__ == "__main__":
    main()