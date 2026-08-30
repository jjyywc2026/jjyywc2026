import os
import hashlib
import base64
import pathlib
import time
from database import TursoClient, ConfigError, DatabaseError
from app_paths import get_app_dir

# 记住密码有效期：10分钟
REMEMBER_TTL_SECONDS = 600

# ---------- 加密工具（标准库实现，避免Android编译原生依赖） ----------
_cipher_key = None

def _get_key():
    """获取或生成加密密钥（存储在APP_DIR，base64编码）"""
    global _cipher_key
    if _cipher_key is None:
        key_file = get_app_dir() / "secret.key"
        if key_file.exists():
            try:
                raw = key_file.read_bytes()
                _cipher_key = base64.b64decode(raw)
                if len(_cipher_key) != 32:
                    raise ValueError("key length mismatch")
            except Exception:
                # 旧版cryptography生成的key格式不兼容，删除重建
                try:
                    key_file.unlink()
                except Exception:
                    pass
                _cipher_key = None
        if _cipher_key is None:
            _cipher_key = os.urandom(32)
            key_file.write_bytes(base64.b64encode(_cipher_key))
    return _cipher_key

def _xor(data, key):
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def encrypt_pwd(pwd):
    if not pwd:
        return ""
    key = _get_key()
    encrypted = _xor(pwd.encode("utf-8"), key)
    return base64.b64encode(encrypted).decode()

def decrypt_pwd(encrypted):
    try:
        if not encrypted:
            return ""
        key = _get_key()
        raw = base64.b64decode(encrypted.encode())
        return _xor(raw, key).decode("utf-8")
    except Exception:
        return ""

def _config_file():
    return get_app_dir() / "login_config.txt"

def save_login_config(username, password, auto):
    """保存登录配置，格式：username\nencrypted_pwd\nauto\ntimestamp"""
    ts = str(int(time.time()))
    _config_file().write_text(f"{username}\n{encrypt_pwd(password)}\n{str(auto)}\n{ts}", encoding="utf-8")

def load_login_config():
    """读取登录配置，超过10分钟则密码过期（仅保留用户名）"""
    cf = _config_file()
    if not cf.exists():
        return None, None, False
    try:
        lines = cf.read_text(encoding="utf-8").splitlines()
        if len(lines) >= 3:
            username = lines[0].strip()
            pwd = decrypt_pwd(lines[1].strip()) if len(lines) > 1 else ""
            auto = lines[2].strip() == "True" if len(lines) > 2 else False
            # 检查时间戳（第4行），超过10分钟则密码失效
            if len(lines) >= 4:
                try:
                    saved_ts = int(lines[3].strip())
                    if time.time() - saved_ts > REMEMBER_TTL_SECONDS:
                        # 过期：清空密码和自动登录，保留用户名
                        return username, "", False
                except (ValueError, IndexError):
                    pass
            return username, pwd, auto
    except:
        pass
    return None, None, False

# ---------- 认证服务 ----------
class AuthService:
    def __init__(self):
        self.db = TursoClient()

    def reload_config(self):
        self.db.reload_config()

    def login(self, username, password):
        if not username or not password:
            return False, "请输入用户名和密码", None
        try:
            user = self.db.fetch_one(
                "SELECT user_id, user_type, score, level_id, user_status, password, sync_enabled FROM users WHERE username = ?",
                [username]
            )
        except Exception as e:
            # sync_enabled列可能尚未添加，降级查询
            err_str = str(e).lower()
            if "sync_enabled" in err_str or "no such column" in err_str:
                try:
                    user = self.db.fetch_one(
                        "SELECT user_id, user_type, score, level_id, user_status, password FROM users WHERE username = ?",
                        [username]
                    )
                except Exception as e2:
                    return False, f"⚠️ 数据库请求失败: {e2}", None
            else:
                return False, f"⚠️ 数据库请求失败: {e}", None

        if user is None:
            return False, "用户不存在", None

        h1 = hashlib.md5(password.strip().encode()).hexdigest()
        h2 = hashlib.md5(h1.encode()).hexdigest()
        if h2 != user.get("password"):
            return False, "密码错误", None

        status = user.get("user_status")
        if status == 1:
            return False, "账号已禁用", None
        if status == 2:
            return False, "账号已冻结", None
        if status == 3:
            return False, "账号已封禁", None
        if status == 4:
            return False, "账号注销中", None
        if status == 5:
            return False, "账号已注销", None

        # sync_enabled可能从云端返回字符串"0"，需转int判断
        try:
            sync_val = int(user.get("sync_enabled", 1))
        except (ValueError, TypeError):
            sync_val = 1
        user_data = {
            "id": user.get("user_id"),
            "username": username,
            "type": user.get("user_type"),
            "score": user.get("score"),
            "level_id": user.get("level_id"),
            "sync_enabled": sync_val,
        }
        return True, "登录成功", user_data
