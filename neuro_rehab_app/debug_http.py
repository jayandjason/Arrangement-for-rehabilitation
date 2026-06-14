import requests
import time

time.sleep(2)

session = requests.Session()

# 获取登录页面，获取 CSRF token（如果有）
login_page = session.get('http://127.0.0.1:5000/login')
print(f"登录页面状态码: {login_page.status_code}")

# 登录
login_data = {'username': 'admin', 'password': '123456'}
login_response = session.post('http://127.0.0.1:5000/login', data=login_data, allow_redirects=False)
print(f"登录状态码: {login_response.status_code}")
print(f"登录响应头: {login_response.headers}")

if login_response.status_code == 302:
    # 查看重定向位置
    redirect_url = login_response.headers.get('Location')
    print(f"重定向到: {redirect_url}")

    # 访问看板
    dashboard_url = 'http://127.0.0.1:5000/dashboard'
    print(f"请求 URL: {dashboard_url}")

    dashboard_response = session.get(dashboard_url, allow_redirects=False)
    print(f"看板状态码: {dashboard_response.status_code}")
    print(f"看板响应头: {dashboard_response.headers}")

    if dashboard_response.status_code == 302:
        # 可能是重定向到登录页面
        print(f"重定向到: {dashboard_response.headers.get('Location')}")
    elif dashboard_response.status_code == 500:
        print("失败！看板页面返回错误。")
        print(dashboard_response.text[:1000])
    else:
        print("成功！看板页面正常工作。")
        if 'v1.2.0' in dashboard_response.text:
            print("版本号显示正确")
        if '治疗项目' in dashboard_response.text:
            print("治疗项目列显示正确")
