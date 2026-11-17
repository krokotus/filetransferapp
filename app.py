import argparse
import io
import socket

import qrcode
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

import config
from security import SecurityManager
from storage import Storage

app = FastAPI(title="Local File Share")
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
security = SecurityManager()
storage = Storage(config.DATA_DIR)

# CORS не нужен для интерфейса, который обслуживается тем же приложением.
# Оставляем middleware без разрешённых внешних origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


def require_session(request: Request) -> str:
    token = request.cookies.get(config.COOKIE_NAME)
    if not security.validate_session(token):
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return token


def local_ip() -> str:
    """Определяет локальный IPv4-адрес для показа ссылки в локальной сети."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def print_qr(url: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    output = io.StringIO()
    qr.print_ascii(out=output, invert=True)
    print(output.getvalue())



@app.on_event("startup")
def on_startup():
    pin, _ = security.current_pin()

    lan_mode = getattr(app.state, "lan_mode", False)
    host = local_ip() if lan_mode else "127.0.0.1"

    url = f"http://{host}:{config.PORT}/"

    print("\n=== Local File Share ===")
    print(f"Адрес: {url}")
    print(f"PIN (действует {config.PIN_TTL_SECONDS // 60} мин.): {pin}")
    print("Открой адрес в браузере и введи PIN.\n")

    print_qr(url)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    token = request.cookies.get(config.COOKIE_NAME)
    authenticated = bool(security.validate_session(token))
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"authed": authenticated},
    )


@app.post("/login")
def login(request: Request, pin: str = Form(...)):
    ip = request.client.host if request.client else "unknown"
    if not security.verify_pin(ip, pin):
        return JSONResponse(
            {"ok": False, "error": "Неверный PIN или превышено число попыток"},
            status_code=401,
        )

    session = security.create_session()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key=config.COOKIE_NAME,
        value=session.token,
        httponly=True,
        samesite="strict",
        secure=config.COOKIE_SECURE,
        max_age=config.SESSION_TTL_SECONDS,
        path="/",
    )
    return response


@app.post("/logout")
def logout(token: str = Depends(require_session)):
    security.sessions.pop(token, None)
    response = JSONResponse({"ok": True})
    response.delete_cookie(config.COOKIE_NAME, path="/")
    return response


@app.get("/api/files")
def list_files(_: str = Depends(require_session)):
    return storage.list_files()


@app.post("/api/upload")
async def upload(
    token: str = Depends(require_session),
    file: UploadFile = File(...),
):
    # Сначала проверяем общий лимит числа сохранённых файлов.
    if len(storage.list_files()) >= config.MAX_FILES_TOTAL:
        raise HTTPException(status_code=400, detail="Достигнут лимит количества файлов")

    try:
        saved = await storage.save_upload(file.filename or "file", file)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    finally:
        await file.close()
    return saved


@app.get("/api/download/{file_id}")
def download(file_id: str, _: str = Depends(require_session)):
    try:
        path, original_name = storage.get_paths(file_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Файл не найден")

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=original_name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.delete("/api/files/{file_id}")
def delete(file_id: str, _: str = Depends(require_session)):
    try:
        storage.delete(file_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return {"ok": True}


def main():
    parser = argparse.ArgumentParser(description="Локальный обмен файлами")
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Разрешить подключения с других устройств локальной сети",
    )
    args = parser.parse_args()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    if args.lan:
        print("ВНИМАНИЕ: сервер будет доступен устройствам локальной сети.")
        print("Используйте его только в доверенной сети; HTTP не шифрует трафик.")
    uvicorn.run(app, host=host, port=config.PORT)


if __name__ == "__main__":
    main()
