import requests
import time

time.sleep(2)

session = requests.Session()

# 登录
login_data = {'username': 'admin', 'password': '123456'}
response = session.post('http://127.0.0.1:5000/login', data=login_data, allow_redirects=False)
print(f"登录状态码: {response.status_code}")

if response.status_code == 302:
    # 访问看板
    dashboard_response = session.get('http://127.0.0.1:5000/dashboard')
    print(f"看板状态码: {dashboard_response.status_code}")

    if dashboard_response.status_code == 200:
        print("成功！看板页面正常工作。")
        if 'v1.2.0' in dashboard_response.text:
            print("版本号显示正确")
        if '治疗项目' in dashboard_response.text:
            print("治疗项目列显示正确")
    else:
        print("失败！看板页面返回错误。")
        print(dashboard_response.text[:500])
