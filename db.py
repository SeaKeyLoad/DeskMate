import mysql.connector
import json
import os
import hashlib
from datetime import datetime
from typing import Dict, Optional, Any

# MySQL 配置
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'ai_chat'
}


class DBManager:
    def __init__(self):
        self.use_mysql = False
        self.json_path = "users.json"
        self._init_db()

    def _init_db(self):
        """初始化数据库：优先使用MySQL，失败则降级到JSON文件"""
        try:
            # 尝试连接 MySQL
            with mysql.connector.connect(
                    host=MYSQL_CONFIG['host'],
                    user=MYSQL_CONFIG['user'],
                    password=MYSQL_CONFIG['password']
            ) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']}")
                    conn.database = MYSQL_CONFIG['database']

                    # 创建用户表（包含 model_mode 字段）
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            username VARCHAR(50) UNIQUE NOT NULL,
                            password VARCHAR(255) NOT NULL,
                            role VARCHAR(20) DEFAULT 'user',
                            model_mode INT(2) DEFAULT 0,
                            last_session_id VARCHAR(50),
                            last_login_ip VARCHAR(50),
                            last_login_device VARCHAR(255),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # 确保旧表存在 model_mode 字段（兼容迁移）
                    try:
                        cursor.execute("""
                            ALTER TABLE users 
                            ADD COLUMN model_mode INT(2) DEFAULT 0
                        """)
                    except mysql.connector.Error as e:
                        # 忽略"字段已存在"错误 (Error 1060)
                        if e.errno != 1060:
                            raise

            self.use_mysql = True
            print("✅ 数据库模式: MySQL")
        except Exception as e:
            self.use_mysql = False
            print(f"⚠️ MySQL 连接失败: {e}")
            print("📂 数据库模式: JSON 文件降级")
            if not os.path.exists(self.json_path):
                with open(self.json_path, 'w') as f:
                    json.dump({}, f)

    def _get_mysql_conn(self):
        """获取MySQL连接（带异常处理）"""
        try:
            return mysql.connector.connect(**MYSQL_CONFIG)
        except mysql.connector.Error as e:
            print(f"❌ MySQL 连接错误: {e}")
            raise

    def hash_password(self, password: str) -> str:
        """密码哈希处理"""
        return hashlib.sha256(password.encode()).hexdigest()

    def register_user(self, username: str, password: str, role: str = 'user') -> bool:
        """注册新用户"""
        pwd_hash = self.hash_password(password)
        model_mode = 0  # 默认模型模式

        if self.use_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO users (username, password, role, model_mode) VALUES (%s, %s, %s, %s)",
                            (username, pwd_hash, role, model_mode)
                        )
                    conn.commit()
                return True
            except mysql.connector.Error as e:
                if e.errno == 1062:  # Duplicate entry
                    return False
                raise
        else:
            with open(self.json_path, 'r+') as f:
                data = json.load(f)
                if username in data:
                    return False
                data[username] = {
                    "password": pwd_hash,
                    "role": role,
                    "model_mode": model_mode,
                    "id": str(len(data) + 1)
                }
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
            return True

    def verify_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """验证用户登录并返回完整用户信息"""
        pwd_hash = self.hash_password(password)

        if self.use_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor(dictionary=True) as cursor:
                        cursor.execute(
                            "SELECT id, username, role, model_mode FROM users WHERE username = %s AND password = %s",
                            (username, pwd_hash)
                        )
                        user = cursor.fetchone()
                if user:
                    return {
                        "id": str(user['id']),
                        "username": user['username'],
                        "role": user['role'],
                        "model_mode": user.get('model_mode', 0)  # 兼容旧数据
                    }
                return None
            except mysql.connector.Error as e:
                print(f"❌ 验证用户时MySQL错误: {e}")
                return None
        else:
            try:
                with open(self.json_path, 'r') as f:
                    data = json.load(f)
                user = data.get(username)
                if user and user['password'] == pwd_hash:
                    return {
                        "id": user['id'],
                        "username": username,
                        "role": user['role'],
                        "model_mode": user.get('model_mode', 0)  # 默认值0
                    }
                return None
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"❌ JSON读取错误: {e}")
                return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """通过用户ID获取用户信息"""
        if self.use_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor(dictionary=True) as cursor:
                        cursor.execute(
                            "SELECT id, username, role, model_mode, last_session_id, last_login_ip, last_login_device FROM users WHERE id = %s",
                            (user_id,)
                        )
                        user = cursor.fetchone()
                if user:
                    return {
                        k: str(v) if isinstance(v, (int, datetime)) else v
                        for k, v in user.items() if v is not None
                    }
                return None
            except mysql.connector.Error as e:
                print(f"❌ 获取用户时MySQL错误: {e}")
                return None
        else:
            try:
                with open(self.json_path, 'r') as f:
                    data = json.load(f)
                for uname, info in data.items():
                    if info['id'] == str(user_id):
                        return {
                            "id": info['id'],
                            "username": uname,
                            "role": info['role'],
                            "model_mode": info.get('model_mode', 0),
                            "last_session_id": info.get('last_session_id'),
                            "last_login_ip": info.get('last_login_ip'),
                            "last_login_device": info.get('last_login_device')
                        }
                return None
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"❌ JSON读取错误: {e}")
                return None

    def update_user_model_mode(self, user_id: str, model_mode: int) -> bool:
        """更新用户的模型模式 (0=本地, 1=线上)"""
        if not isinstance(model_mode, int) or model_mode < 0 or model_mode > 99:
            raise ValueError("model_mode 必须是 0-99 的整数")

        if self.use_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE users SET model_mode = %s WHERE id = %s",
                            (model_mode, user_id)
                        )
                    conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error as e:
                print(f"❌ 更新model_mode时MySQL错误: {e}")
                return False
        else:
            return self._update_json_user(user_id, {'model_mode': model_mode})

    def get_user_model_mode(self, user_id: str) -> Optional[int]:
        """
        获取指定用户的 model_mode 值

        Args:
            user_id: 用户ID（字符串格式）

        Returns:
            int: 用户的模型模式值（0-99），未找到用户时返回 None

        Example:
            mode = db.get_user_model_mode("123")
            if mode == 0:
                use_basic_model()
            elif mode == 1:
                use_advanced_model()
        """
        if self.use_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor(dictionary=True) as cursor:
                        cursor.execute(
                            "SELECT model_mode FROM users WHERE id = %s",
                            (user_id,)
                        )
                        result = cursor.fetchone()
                return result['model_mode'] if result else None
            except mysql.connector.Error as e:
                print(f"⚠️ 获取 model_mode 时 MySQL 错误: {e}")
                return None
        else:
            try:
                with open(self.json_path, 'r') as f:
                    data = json.load(f)
                for info in data.values():
                    if info.get('id') == str(user_id):
                        return info.get('model_mode', 0)  # 兼容旧数据
                return None
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"⚠️ 获取 model_mode 时 JSON 错误: {e}")
                return None

    def log_user_login(self, user_id: str, ip: str, device: str) -> None:
        """记录用户登录信息"""
        if self.use_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE users SET last_login_ip=%s, last_login_device=%s WHERE id=%s",
                            (ip, device, user_id)
                        )
                    conn.commit()
            except mysql.connector.Error as e:
                print(f"⚠️ 登录记录失败: {e}")
        else:
            self._update_json_user(user_id, {'last_login_ip': ip, 'last_login_device': device})

    def update_last_session(self, user_id: str, session_id: str) -> None:
        """更新用户最后会话ID"""
        if self.use_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE users SET last_session_id=%s WHERE id=%s",
                            (session_id, user_id)
                        )
                    conn.commit()
            except mysql.connector.Error as e:
                print(f"⚠️ 会话更新失败: {e}")
        else:
            self._update_json_user(user_id, {'last_session_id': session_id})

    def get_user_last_session(self, user_id: str) -> Optional[str]:
        """获取用户最后会话ID"""
        user = self.get_user_by_id(user_id)
        return user.get('last_session_id') if user else None

    def _update_json_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """JSON模式下更新用户数据的通用方法"""
        try:
            with open(self.json_path, 'r+') as f:
                data = json.load(f)
                for uname, info in data.items():
                    if info['id'] == str(user_id):
                        info.update(updates)
                        f.seek(0)
                        json.dump(data, f, indent=4)
                        f.truncate()
                        return True
                return False
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"❌ JSON更新错误: {e}")
            return False


# 全局数据库实例
db = DBManager()