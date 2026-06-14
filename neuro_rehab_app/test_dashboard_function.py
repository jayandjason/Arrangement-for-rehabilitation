import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import app, init_db

    # 初始化数据库
    init_db()

    # 使用测试客户端
    with app.test_client() as client:
        # 模拟登录
        with client.session_transaction() as sess:
            sess['user'] = {'id': 1, 'username': 'admin', 'role': 'admin', 'real_name': '系统管理员'}

        # 尝试访问看板页面
        try:
            response = client.get('/dashboard')
            print(f"看板页面状态码: {response.status_code}")

            if response.status_code == 500:
                print("服务器错误详情:")
                print(response.data.decode('utf-8'))
            else:
                print("页面访问成功")
                # 检查内容
                text = response.data.decode('utf-8')
                if 'v2.0.0' in text:
                    print("版本号显示正确")
                else:
                    print("版本号未显示")
                if '治疗项目' in text:
                    print("治疗项目列显示正确")
                else:
                    print("治疗项目列未显示")

        except Exception as e:
            print(f"请求失败: {e}")
            import traceback
            traceback.print_exc()

except Exception as e:
    print(f"测试失败: {e}")
    import traceback
    traceback.print_exc()
