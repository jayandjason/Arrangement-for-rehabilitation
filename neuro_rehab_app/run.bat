@echo off
chcp 65001 >nul
echo ========================================
echo 神经心理康复中心病人预约管理系统
echo ========================================
echo.
echo 正在启动服务...
echo.
echo 请在浏览器中访问: http://localhost:5000
echo.
echo 默认账号:
echo   预约端: appointment / appointment123
echo   安排端: schedule / schedule123
echo   看板端: dashboard / dashboard123
echo.
echo 按 Ctrl+C 停止服务
echo ========================================
echo.

python app.py
