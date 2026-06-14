from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from datetime import datetime, timedelta
import sqlite3
import os
import csv
import io
import shutil
import threading
import time
from functools import wraps

# Debug log file path
debug_log_path = os.path.join(os.path.dirname(__file__), 'debug.log')

app = Flask(__name__)
app.secret_key = 'neuro_rehab_secret_key_2024'
app.config['DATABASE'] = 'neuro_rehab.db'
app.config['VERSION'] = '2.0.0'

# 确保 static 和 templates 目录存在
os.makedirs('static', exist_ok=True)
os.makedirs('templates', exist_ok=True)

def get_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 创建患者表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            phone TEXT,
            diagnosis TEXT,
            patient_type TEXT CHECK(patient_type IN ('新病人', '老病人')),
            specialty_group TEXT,
            main_obstacle TEXT,
            visit_type TEXT CHECK(visit_type IN ('住院', '门诊')),
            doctor TEXT,
            treatment_project TEXT,
            appointment_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_cancelled INTEGER DEFAULT 0,
            cancelled_reason TEXT,
            modified_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 检查并添加phone字段（如果表已存在）
    cursor.execute("PRAGMA table_info(patients)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'phone' not in columns:
        cursor.execute('ALTER TABLE patients ADD COLUMN phone TEXT')

    # 检查并添加treatment_project字段（如果表已存在）
    if 'treatment_project' not in columns:
        cursor.execute('ALTER TABLE patients ADD COLUMN treatment_project TEXT')

    # 创建治疗安排表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            is_scheduled INTEGER DEFAULT 0,
            schedule_reason TEXT,
            primary_therapist TEXT,
            secondary_therapist TEXT,
            schedule_time TIMESTAMP,
            visit_type TEXT CHECK(visit_type IN ('住院', '门诊')),
            created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id)
        )
    ''')

    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT,
            real_name TEXT
        )
    ''')

    # 插入默认用户（仅在首次创建时）
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        default_users = [
            ('admin', 'admin123', 'admin', '系统管理员'),
            ('appointment', 'appointment123', 'appointment', '预约员'),
            ('schedule', 'schedule123', 'schedule', '安排员'),
            ('dashboard', 'dashboard123', 'dashboard', '看板员')
        ]
        for user in default_users:
            cursor.execute('INSERT INTO users (username, password, role, real_name) VALUES (?, ?, ?, ?)', user)

    conn.commit()
    conn.close()

def find_duplicate_appointment(cursor, name, age, phone, exclude_patient_id=None):
    """查找同一患者当前未取消且未安排完成的预约，避免重复录入。
    已安排完成的患者（is_scheduled=1）视为旧预约已完成，不阻止新预约录入。"""
    params = [name]
    where_conditions = ['p.is_cancelled = 0', 'p.name = ?']

    if phone:
        where_conditions.append('p.phone = ?')
        params.append(phone)
    else:
        where_conditions.append('p.age = ?')
        params.append(age)

    if exclude_patient_id:
        where_conditions.append('p.id != ?')
        params.append(exclude_patient_id)

    cursor.execute(f'''
        SELECT p.id, p.name, p.age, p.phone, p.doctor, p.appointment_time
        FROM patients p
        LEFT JOIN schedules s ON p.id = s.patient_id
        WHERE {' AND '.join(where_conditions)}
          AND (s.is_scheduled IS NULL OR s.is_scheduled != 1)
        ORDER BY p.appointment_time DESC
        LIMIT 1
    ''', params)
    return cursor.fetchone()

def duplicate_appointment_message(patient):
    doctor = patient['doctor'] or '-'
    appointment_time = patient['appointment_time'] or '-'
    return f'存在重复预约：{patient["name"]} 已在 {appointment_time} 预约（预约医生：{doctor}），请修改原预约或先取消原预约后再录入。'

def login_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                if 'user' not in session:
                    return redirect(url_for('login'))
                # 支持多个角色（用逗号分隔）或单个角色
                allowed_roles = [r.strip() for r in role.split(',')] if isinstance(role, str) else role
                if session['user']['role'] not in allowed_roles:
                    flash('无权访问此页面', 'error')
                    return redirect(url_for('login'))
                return f(*args, **kwargs)
            except Exception as e:
                print(f"Login required error: {e}")
                import traceback
                traceback.print_exc()
                raise
        return decorated_function
    return decorator

@app.route('/')
def index():
    with open(debug_log_path, 'a') as f:
        f.write(f"Index route accessed at {datetime.now()}\n")
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    with open(debug_log_path, 'a') as f:
        f.write(f"Login route accessed at {datetime.now()}\n")
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'real_name': user['real_name']
            }

            if user['role'] == 'appointment':
                return redirect(url_for('appointment'))
            elif user['role'] == 'schedule':
                return redirect(url_for('schedule'))
            elif user['role'] == 'dashboard':
                return redirect(url_for('dashboard'))
            elif user['role'] == 'admin':
                return redirect(url_for('dashboard'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin/accounts')
@login_required('admin')
def admin_accounts():
    """管理员账户管理页面"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT id, username, role, real_name FROM users ORDER BY id')
    users = cursor.fetchall()

    conn.close()
    return render_template('admin_accounts.html', users=users)

@app.route('/admin/create_account', methods=['POST'])
@login_required('admin')
def create_account():
    """创建新账户"""
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    real_name = request.form['real_name']

    conn = get_db()
    cursor = conn.cursor()

    # 检查用户名是否已存在
    cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', (username,))
    if cursor.fetchone()[0] > 0:
        flash('用户名已存在', 'error')
        return redirect(url_for('admin_accounts'))

    # 创建新用户
    cursor.execute('''
        INSERT INTO users (username, password, role, real_name)
        VALUES (?, ?, ?, ?)
    ''', (username, password, role, real_name))

    conn.commit()
    conn.close()

    flash('账户创建成功', 'success')
    return redirect(url_for('admin_accounts'))

@app.route('/admin/delete_account/<int:user_id>', methods=['POST'])
@login_required('admin')
def delete_account(user_id):
    """删除账户"""
    # 防止删除自己
    if session['user']['id'] == user_id:
        flash('不能删除自己的账户', 'error')
        return redirect(url_for('admin_accounts'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))

    conn.commit()
    conn.close()

    flash('账户删除成功', 'success')
    return redirect(url_for('admin_accounts'))

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    """修改密码"""
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # 验证新密码和确认密码是否一致
        if new_password != confirm_password:
            flash('新密码和确认密码不一致', 'error')
            return redirect(url_for('change_password'))

        conn = get_db()
        cursor = conn.cursor()

        # 验证当前密码
        cursor.execute('SELECT password FROM users WHERE id = ?', (session['user']['id'],))
        user = cursor.fetchone()

        if user and user['password'] == current_password:
            # 更新密码
            cursor.execute('UPDATE users SET password = ? WHERE id = ?',
                         (new_password, session['user']['id']))
            conn.commit()
            conn.close()

            flash('密码修改成功', 'success')
            return redirect(url_for('change_password'))
        else:
            conn.close()
            flash('当前密码错误', 'error')
            return redirect(url_for('change_password'))

    return render_template('change_password.html')

@app.route('/appointment')
@login_required('appointment,admin')
def appointment():
    conn = get_db()
    cursor = conn.cursor()

    # 获取所有未取消的预约，按预约时间排序
    cursor.execute('''
        SELECT p.*, s.is_scheduled, s.schedule_time
        FROM patients p
        LEFT JOIN schedules s ON p.id = s.patient_id
        WHERE p.is_cancelled = 0
        ORDER BY p.appointment_time DESC
    ''')
    patients = cursor.fetchall()

    conn.close()
    return render_template('appointment.html', patients=patients)

@app.route('/add_patient', methods=['POST'])
@login_required('appointment,admin')
def add_patient():
    conn = get_db()
    cursor = conn.cursor()

    name = request.form['name'].strip()
    age = int(request.form['age'])
    phone = request.form.get('phone', '').strip()
    diagnosis = request.form.get('diagnosis', '').strip()
    main_obstacle = request.form.get('main_obstacle', '').strip()
    doctor = request.form['doctor'].strip()
    treatment_project = request.form.get('treatment_project', '').strip()

    duplicate_patient = find_duplicate_appointment(cursor, name, age, phone)
    if duplicate_patient:
        conn.close()
        flash(duplicate_appointment_message(duplicate_patient), 'error')
        return redirect(url_for('appointment'))

    cursor.execute('''
        INSERT INTO patients (name, age, phone, diagnosis, patient_type, specialty_group, main_obstacle, visit_type, doctor, treatment_project)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        name,
        age,
        phone,
        diagnosis,
        request.form['patient_type'],
        request.form['specialty_group'],
        main_obstacle,
        request.form['visit_type'],
        doctor,
        treatment_project
    ))

    patient_id = cursor.lastrowid

    # 同时创建对应的安排记录
    cursor.execute('''
        INSERT INTO schedules (patient_id, visit_type)
        VALUES (?, ?)
    ''', (patient_id, request.form['visit_type']))

    conn.commit()
    conn.close()

    flash('患者信息添加成功', 'success')
    return redirect(url_for('appointment'))

@app.route('/update_patient/<int:patient_id>', methods=['POST'])
@login_required('appointment,admin')
def update_patient(patient_id):
    conn = get_db()
    cursor = conn.cursor()

    name = request.form['name'].strip()
    age = int(request.form['age'])
    phone = request.form.get('phone', '').strip()
    diagnosis = request.form.get('diagnosis', '').strip()
    main_obstacle = request.form.get('main_obstacle', '').strip()
    doctor = request.form['doctor'].strip()
    treatment_project = request.form.get('treatment_project', '').strip()

    duplicate_patient = find_duplicate_appointment(cursor, name, age, phone, patient_id)
    if duplicate_patient:
        conn.close()
        flash(duplicate_appointment_message(duplicate_patient), 'error')
        return redirect(url_for('appointment'))

    cursor.execute('''
        UPDATE patients
        SET name = ?, age = ?, phone = ?, diagnosis = ?, patient_type = ?, specialty_group = ?,
            main_obstacle = ?, visit_type = ?, doctor = ?, treatment_project = ?, modified_time = CURRENT_TIMESTAMP
        WHERE id = ? AND is_cancelled = 0
    ''', (
        name,
        age,
        phone,
        diagnosis,
        request.form['patient_type'],
        request.form['specialty_group'],
        main_obstacle,
        request.form['visit_type'],
        doctor,
        treatment_project,
        patient_id
    ))

    cursor.execute('''
        UPDATE schedules
        SET visit_type = ?
        WHERE patient_id = ?
    ''', (request.form['visit_type'], patient_id))

    conn.commit()
    conn.close()

    flash('患者信息更新成功', 'success')
    return redirect(url_for('appointment'))

@app.route('/cancel_patient/<int:patient_id>', methods=['POST'])
@login_required('appointment,admin')
def cancel_patient(patient_id):
    conn = get_db()
    cursor = conn.cursor()

    cancel_reason = request.form.get('cancel_reason', '').strip()
    if not cancel_reason:
        conn.close()
        flash('取消预约必须填写取消原因', 'error')
        return redirect(url_for('appointment'))

    cursor.execute('''
        UPDATE patients
        SET is_cancelled = 1, cancelled_reason = ?, modified_time = CURRENT_TIMESTAMP
        WHERE id = ? AND is_cancelled = 0
    ''', (cancel_reason, patient_id))

    conn.commit()
    conn.close()

    flash('预约已取消', 'success')
    return redirect(url_for('appointment'))

@app.route('/schedule')
@login_required('schedule,admin')
def schedule():
    conn = get_db()
    cursor = conn.cursor()

    # 获取所有未安排的患者
    specialty_group = request.args.get('specialty_group', '')

    if specialty_group:
        cursor.execute('''
            SELECT p.*, s.is_scheduled, s.schedule_time, s.primary_therapist, s.secondary_therapist,
                   s.schedule_reason, julianday('now') - julianday(s.created_time) as days_pending
            FROM patients p
            JOIN schedules s ON p.id = s.patient_id
            WHERE p.is_cancelled = 0 AND s.is_scheduled = 0 AND p.specialty_group = ?
            ORDER BY p.appointment_time
        ''', (specialty_group,))
    else:
        cursor.execute('''
            SELECT p.*, s.is_scheduled, s.schedule_time, s.primary_therapist, s.secondary_therapist,
                   s.schedule_reason, julianday('now') - julianday(s.created_time) as days_pending
            FROM patients p
            JOIN schedules s ON p.id = s.patient_id
            WHERE p.is_cancelled = 0 AND s.is_scheduled = 0
            ORDER BY p.appointment_time
        ''')

    patients = cursor.fetchall()

    # 获取已完成安排的患者
    if specialty_group:
        cursor.execute('''
            SELECT p.*, s.is_scheduled, s.schedule_time, s.primary_therapist, s.secondary_therapist,
                   s.schedule_reason
            FROM patients p
            JOIN schedules s ON p.id = s.patient_id
            WHERE p.is_cancelled = 0 AND s.is_scheduled = 1 AND p.specialty_group = ?
            ORDER BY s.schedule_time DESC
        ''', (specialty_group,))
    else:
        cursor.execute('''
            SELECT p.*, s.is_scheduled, s.schedule_time, s.primary_therapist, s.secondary_therapist,
                   s.schedule_reason
            FROM patients p
            JOIN schedules s ON p.id = s.patient_id
            WHERE p.is_cancelled = 0 AND s.is_scheduled = 1
            ORDER BY s.schedule_time DESC
        ''')

    scheduled_patients = cursor.fetchall()

    # 获取拒绝安排的患者
    if specialty_group:
        cursor.execute('''
            SELECT p.*, s.is_scheduled, s.schedule_time, s.primary_therapist, s.secondary_therapist,
                   s.schedule_reason, julianday('now') - julianday(s.created_time) as days_pending
            FROM patients p
            JOIN schedules s ON p.id = s.patient_id
            WHERE p.is_cancelled = 0 AND s.is_scheduled = 2 AND p.specialty_group = ?
            ORDER BY s.schedule_time DESC
        ''', (specialty_group,))
    else:
        cursor.execute('''
            SELECT p.*, s.is_scheduled, s.schedule_time, s.primary_therapist, s.secondary_therapist,
                   s.schedule_reason, julianday('now') - julianday(s.created_time) as days_pending
            FROM patients p
            JOIN schedules s ON p.id = s.patient_id
            WHERE p.is_cancelled = 0 AND s.is_scheduled = 2
            ORDER BY s.schedule_time DESC
        ''')

    rejected_patients = cursor.fetchall()

    # 获取所有专业组
    cursor.execute('SELECT DISTINCT specialty_group FROM patients WHERE is_cancelled = 0 AND specialty_group IS NOT NULL')
    specialty_groups = [row[0] for row in cursor.fetchall()]

    conn.close()
    return render_template('schedule.html', patients=patients, scheduled_patients=scheduled_patients,
                          rejected_patients=rejected_patients, specialty_groups=specialty_groups,
                          selected_group=specialty_group)

@app.route('/schedule_patient/<int:patient_id>', methods=['POST'])
@login_required('schedule,admin')
def schedule_patient(patient_id):
    # is_scheduled: 0=待安排, 1=已安排, 2=拒绝安排
    if request.form.get('is_scheduled') == '1':
        is_scheduled = 1
        schedule_reason = None
    else:
        is_scheduled = 2  # 拒绝安排
        schedule_reason = request.form.get('schedule_reason', '').strip()

    # 验证：如果选择不安排，必须填写原因
    if is_scheduled == 2 and not schedule_reason:
        flash('选择不安排时必须填写原因', 'error')
        return redirect(url_for('schedule'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE schedules
        SET is_scheduled = ?, schedule_reason = ?, primary_therapist = ?, secondary_therapist = ?,
            schedule_time = ?, visit_type = ?
        WHERE patient_id = ?
    ''', (
        is_scheduled,
        schedule_reason,
        request.form.get('primary_therapist', ''),
        request.form.get('secondary_therapist', ''),
        request.form.get('schedule_time', None),
        request.form.get('visit_type', ''),
        patient_id
    ))

    conn.commit()
    conn.close()

    if is_scheduled == 1:
        flash('治疗安排已更新', 'success')
    else:
        flash('已标记为不安排治疗', 'success')
    return redirect(url_for('schedule'))

@app.route('/dashboard')
@login_required('dashboard,admin')
def dashboard():
    with open(debug_log_path, 'a') as f:
        f.write(f"Dashboard route accessed at {datetime.now()}\n")
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 获取时间范围参数
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')

        # 构建查询条件
        where_conditions = ['1 = 1']
        params = []

        if start_date:
            where_conditions.append('p.appointment_time >= ?')
            params.append(start_date)
        if end_date:
            where_conditions.append('p.appointment_time <= ?')
            params.append(end_date + ' 23:59:59')

        where_clause = ' AND '.join(where_conditions)

        # 获取患者信息
        query = f'''
            SELECT p.*, s.is_scheduled, s.schedule_time, s.primary_therapist, s.secondary_therapist, s.schedule_reason
            FROM patients p
            LEFT JOIN schedules s ON p.id = s.patient_id
            WHERE {where_clause}
            ORDER BY p.appointment_time DESC
        '''
        cursor.execute(query, params)
        patients = cursor.fetchall()
        summary_counts = {
            'total_count': len(patients),
            'pending_count': sum(1 for patient in patients if patient['is_cancelled'] == 0 and patient['is_scheduled'] == 0),
            'scheduled_count': sum(1 for patient in patients if patient['is_cancelled'] == 0 and patient['is_scheduled'] == 1),
            'rejected_count': sum(1 for patient in patients if patient['is_cancelled'] == 0 and patient['is_scheduled'] == 2),
            'cancelled_count': sum(1 for patient in patients if patient['is_cancelled'] == 1),
        }

        # 计算平均安排时间（仅计算已安排的）
        query = f'''
            SELECT p.specialty_group,
                   AVG(julianday(s.schedule_time) - julianday(p.appointment_time)) as avg_days
            FROM patients p
            JOIN schedules s ON p.id = s.patient_id
            WHERE {where_clause} AND p.is_cancelled = 0 AND s.is_scheduled = 1 AND s.schedule_time IS NOT NULL
            GROUP BY p.specialty_group
            ORDER BY avg_days DESC
        '''
        cursor.execute(query, params)
        specialty_stats = cursor.fetchall()

        # 按专业组统计数据（区分三种状态）
        query = f'''
            SELECT
                p.specialty_group,
                COUNT(*) as total_count,
                SUM(CASE WHEN p.patient_type = '新病人' THEN 1 ELSE 0 END) as new_count,
                SUM(CASE WHEN p.patient_type = '老病人' THEN 1 ELSE 0 END) as old_count,
                AVG(CASE WHEN p.is_cancelled = 0 AND s.is_scheduled = 1 AND s.schedule_time IS NOT NULL THEN julianday(s.schedule_time) - julianday(p.appointment_time) END) as avg_days,
                SUM(CASE WHEN p.is_cancelled = 0 AND s.is_scheduled = 0 THEN 1 ELSE 0 END) as pending_count,
                SUM(CASE WHEN p.is_cancelled = 0 AND s.is_scheduled = 1 THEN 1 ELSE 0 END) as scheduled_count,
                SUM(CASE WHEN p.is_cancelled = 0 AND s.is_scheduled = 2 THEN 1 ELSE 0 END) as rejected_count,
                SUM(CASE WHEN p.is_cancelled = 1 THEN 1 ELSE 0 END) as cancelled_count
            FROM patients p
            JOIN schedules s ON p.id = s.patient_id
            WHERE {where_clause}
            GROUP BY p.specialty_group
        '''
        cursor.execute(query, params)
        monthly_stats = cursor.fetchall()

        conn.close()
        return render_template('dashboard.html',
                             patients=patients,
                             summary_counts=summary_counts,
                             specialty_stats=specialty_stats,
                             monthly_stats=monthly_stats,
                             start_date=start_date,
                             end_date=end_date)
    except Exception as e:
        # Log the error
        with open(debug_log_path, 'a') as f:
            f.write(f"Dashboard error: {e}\n")
        import traceback
        traceback.print_exc()
        # Re-raise the error to be handled by the error handler
        raise

@app.route('/export_data')
@login_required('dashboard,admin')
def export_data():
    """导出数据为CSV文件"""
    with open(debug_log_path, 'a') as f:
        f.write(f"Export data route accessed at {datetime.now()}\n")
    conn = get_db()
    cursor = conn.cursor()

    # 获取时间范围参数
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    # 构建查询条件
    where_conditions = ['1 = 1']
    params = []

    if start_date:
        where_conditions.append('p.appointment_time >= ?')
        params.append(start_date)
    if end_date:
        where_conditions.append('p.appointment_time <= ?')
        params.append(end_date + ' 23:59:59')

    where_clause = ' AND '.join(where_conditions)

    # 查询数据
    query = f'''
        SELECT p.name, p.age, p.phone, p.diagnosis, p.patient_type, p.specialty_group,
               p.main_obstacle, p.visit_type, p.doctor, p.treatment_project, p.appointment_time,
               p.is_cancelled, p.cancelled_reason,
               s.is_scheduled, s.schedule_time, s.primary_therapist, s.secondary_therapist,
               s.schedule_reason
        FROM patients p
        LEFT JOIN schedules s ON p.id = s.patient_id
        WHERE {where_clause}
        ORDER BY p.appointment_time DESC
    '''
    cursor.execute(query, params)
    data = cursor.fetchall()

    # 创建CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # 写入标题
    writer.writerow(['姓名', '年龄', '电话', '诊断', '患者类型', '专业组', '主要障碍',
                    '就诊类型', '预约医生', '治疗项目', '预约时间', '安排状态', '安排时间',
                    '责任治疗师', '联合治疗师', '安排原因', '取消原因'])

    # 写入数据
    for row in data:
        # 根据is_scheduled值显示不同的状态
        if row['is_cancelled'] == 1:
            status = '已取消'
        elif row['is_scheduled'] == 1:
            status = '已安排'
        elif row['is_scheduled'] == 2:
            status = '拒绝安排'
        else:
            status = '待安排'

        writer.writerow([
            row['name'], row['age'], row['phone'], row['diagnosis'],
            row['patient_type'], row['specialty_group'], row['main_obstacle'],
            row['visit_type'], row['doctor'], row['treatment_project'] or '',
            row['appointment_time'],
            status, row['schedule_time'] or '',
            row['primary_therapist'] or '', row['secondary_therapist'] or '',
            row['schedule_reason'] or '',
            row['cancelled_reason'] or ''
        ])

    conn.close()

    # 创建文件名
    filename = f'患者数据_{start_date or "全部"}_{end_date or "全部"}.csv'
    if start_date == '' and end_date == '':
        filename = f'患者数据_{datetime.now().strftime("%Y%m%d")}.csv'

    # 返回CSV文件
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@app.route('/backup_database')
@login_required('dashboard,admin')
def backup_database():
    """备份数据库"""
    try:
        # 创建备份目录
        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)

        # 创建备份文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(backup_dir, f'neuro_rehab_backup_{timestamp}.db')

        # 复制数据库文件
        shutil.copy2('neuro_rehab.db', backup_file)

        # 清理旧备份（保留最近10个）
        backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')])
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                os.remove(os.path.join(backup_dir, old_backup))

        flash(f'数据库备份成功：{backup_file}', 'success')
        return redirect(url_for('dashboard'))

    except Exception as e:
        flash(f'备份失败：{str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/restore_database', methods=['POST'])
@login_required('dashboard,admin')
def restore_database():
    """恢复数据库"""
    try:
        backup_file = request.form.get('backup_file')
        if not backup_file or not os.path.exists(backup_file):
            flash('备份文件不存在', 'error')
            return redirect(url_for('dashboard'))

        # 确认恢复
        shutil.copy2(backup_file, 'neuro_rehab.db')
        flash('数据库恢复成功', 'success')

    except Exception as e:
        flash(f'恢复失败：{str(e)}', 'error')

    return redirect(url_for('dashboard'))

@app.route('/get_backups')
@login_required('dashboard,admin')
def get_backups():
    """获取备份文件列表"""
    backup_dir = 'backups'
    if not os.path.exists(backup_dir):
        return jsonify([])

    backups = []
    for f in os.listdir(backup_dir):
        if f.endswith('.db'):
            filepath = os.path.join(backup_dir, f)
            stat = os.stat(filepath)
            backups.append({
                'name': f,
                'path': filepath,
                'size': f'{stat.st_size / 1024:.1f} KB',
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
            })

    backups.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify(backups)

# 定时备份功能
def scheduled_backup():
    """每天17:30自动备份数据库"""
    while True:
        now = datetime.now()
        # 计算下次备份时间（明天17:30）
        if now.hour < 17 or (now.hour == 17 and now.minute < 30):
            next_backup = now.replace(hour=17, minute=30, second=0, microsecond=0)
        else:
            next_backup = now + timedelta(days=1)
            next_backup = next_backup.replace(hour=17, minute=30, second=0, microsecond=0)

        # 等待到备份时间
        wait_seconds = (next_backup - now).total_seconds()
        time.sleep(wait_seconds)

        # 执行备份
        try:
            backup_dir = 'backups'
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(backup_dir, f'auto_backup_{timestamp}.db')
            shutil.copy2('neuro_rehab.db', backup_file)

            # 清理旧备份（保留最近30个自动备份）
            backups = sorted([f for f in os.listdir(backup_dir) if f.startswith('auto_backup_')])
            if len(backups) > 30:
                for old_backup in backups[:-30]:
                    os.remove(os.path.join(backup_dir, old_backup))

            print(f"[{datetime.now()}] 自动备份完成: {backup_file}")
        except Exception as e:
            print(f"[{datetime.now()}] 自动备份失败: {e}")

# 启动定时备份线程
backup_thread = threading.Thread(target=scheduled_backup, daemon=True)
backup_thread.start()

@app.errorhandler(500)
def internal_server_error(e):
    return f"""
    <h1>500 Internal Server Error</h1>
    <p>错误详情: {e}</p>
    <p>请检查服务器日志获取更多信息。</p>
    """, 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
