#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
神经心理康复中心病人预约管理系统 - 测试脚本
用于验证系统功能是否正常
"""

import sqlite3
import os

def test_database():
    """测试数据库连接和表结构"""
    print("正在测试数据库...")

    if not os.path.exists('neuro_rehab.db'):
        print("错误：数据库文件不存在，请先启动系统创建数据库")
        return False

    try:
        conn = sqlite3.connect('neuro_rehab.db')
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"数据库中存在 {len(tables)} 张表:")
        for table in tables:
            print(f"  - {table[0]}")

        # 检查用户表
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"\n用户数量: {user_count}")

        # 显示用户列表
        cursor.execute("SELECT username, role, real_name FROM users")
        users = cursor.fetchall()
        print("\n用户列表:")
        for user in users:
            print(f"  - {user[0]} ({user[1]}): {user[2]}")

        # 检查患者表
        cursor.execute("SELECT COUNT(*) FROM patients")
        patient_count = cursor.fetchone()[0]
        print(f"\n患者数量: {patient_count}")

        conn.close()
        print("\n数据库测试通过！")
        return True

    except Exception as e:
        print(f"数据库测试失败: {e}")
        return False

def test_flask_app():
    """测试Flask应用"""
    print("\n正在测试Flask应用...")

    try:
        from app import app, init_db
        print("Flask应用导入成功")
        print(f"应用名称: {app.name}")
        print(f"调试模式: {app.debug}")
        print("Flask应用测试通过！")
        return True
    except Exception as e:
        print(f"Flask应用测试失败: {e}")
        return False

def main():
    print("=" * 50)
    print("神经心理康复中心病人预约管理系统 - 测试")
    print("=" * 50)

    # 测试Flask应用
    flask_ok = test_flask_app()

    # 测试数据库
    db_ok = test_database()

    print("\n" + "=" * 50)
    if flask_ok and db_ok:
        print("所有测试通过！系统运行正常。")
    else:
        print("部分测试失败，请检查系统配置。")
    print("=" * 50)

if __name__ == '__main__':
    main()
