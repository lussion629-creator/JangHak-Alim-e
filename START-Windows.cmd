@echo off
chcp 65001 >nul
cd /d %~dp0
where python >nul 2>nul || (echo Python 3.11 이상을 먼저 설치하세요: https://www.python.org/downloads/ & pause & exit /b)
if not exist .venv (python -m venv .venv)
call .venv\Scripts\activate
pip install -q -r requirements.txt
echo.
echo 장학알리미 서버를 시작합니다. 브라우저에서 http://localhost:8000 을 여세요.
echo 같은 Wi-Fi의 휴대폰에서는 http://이 PC의 IP:8000 으로 접속할 수 있습니다.
start "" http://localhost:8000
uvicorn server.app:app --host 0.0.0.0 --port 8000
