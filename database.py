import os
import json
import time
import requests
from pathlib import Path
import datetime
from app_paths import get_app_dir

# ---------- 异常定义 ----------
class ConfigError(Exception):
    pass

class DatabaseError(Exception):
    pass

# ---------- 配置加载 ----------
def load_turso_config():
    config_path = get_app_dir() / "turso-config.json"
    if not config_path.exists():
        config_path = Path.cwd() / "turso-config.json"
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            token = data.get("turso_token")
            raw_url = data.get("turso_url")
            if token and raw_url:
                url = raw_url.strip()
                # 统一转换为 https:// 格式
                if url.startswith("libsql://"):
                    url = "https://" + url[9:]   # 去掉 "libsql://"
                elif url.startswith("http://"):
                    url = url.replace("http://", "https://")
                elif not url.startswith("https://"):
                    url = "https://" + url
                return {"token": token.strip(), "url": url}
        except Exception as e:
            raise ConfigError(f"配置文件解析失败: {e}")
    token = os.getenv("TURSO_TOKEN")
    raw_url = os.getenv("TURSO_URL")
    if token and raw_url:
        url = raw_url.strip()
        if url.startswith("libsql://"):
            url = "https://" + url[9:]
        elif url.startswith("http://"):
            url = url.replace("http://", "https://")
        elif not url.startswith("https://"):
            url = "https://" + url
        return {"token": token.strip(), "url": url}
    return None

# ---------- Turso 客户端 ----------
class TursoClient:
    _col_cache = {}   # 类变量，跨实例共享列名缓存

    def __init__(self):
        self.config = None
        self.url = None
        self.token = None
        self.headers = None
        self._session = None

    def _ensure_config(self):
        if self.config is None:
            cfg = load_turso_config()
            if cfg is None:
                raise ConfigError("未找到有效的 Turso 配置，请到登录页设置")
            self.config = cfg
            self.url = cfg["url"]
            self.token = cfg["token"]
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self.headers)

    def reload_config(self):
        self.config = None
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
        self._ensure_config()

    def close(self):
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def execute(self, sql, params=None):
        self._ensure_config()
        args = []
        for p in (params or []):
            if p is None:
                args.append({"type": "null", "value": None})
            else:
                args.append({"type": "text", "value": str(p)})
        payload = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": args}},
                {"type": "close"}
            ]
        }
        url = self.url.rstrip("/") + "/v2/pipeline"
        last_exception = None
        for attempt in range(3):
            try:
                resp = self._session.post(url, json=payload, timeout=15)
                if resp.status_code != 200:
                    error_detail = ""
                    try:
                        error_data = resp.json()
                        error_detail = error_data.get("error", resp.text)
                    except:
                        error_detail = resp.text
                    raise DatabaseError(f"请求失败 ({resp.status_code}): {error_detail}")
                result = resp.json()
                # 检查SQL执行错误（execute请求不经过_parse_result，需自行检查）
                try:
                    first = result["results"][0]
                    if "error" in first:
                        err = first["error"]
                        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                        raise DatabaseError(f"SQL错误: {msg}")
                    if "response" in first and "error" in first["response"]:
                        err = first["response"]["error"]
                        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                        raise DatabaseError(f"SQL错误: {msg}")
                except (KeyError, IndexError, TypeError):
                    pass
                return result
            except requests.exceptions.ConnectionError as e:
                last_exception = DatabaseError(f"网络连接失败 (尝试 {attempt + 1}/3): {str(e)}")
                time.sleep(0.5)
            except requests.exceptions.Timeout as e:
                last_exception = DatabaseError(f"请求超时 (尝试 {attempt + 1}/3): {str(e)}")
                time.sleep(0.5)
            except requests.exceptions.RequestException as e:
                last_exception = DatabaseError(f"网络请求异常: {str(e)}")
                time.sleep(0.5)
            except DatabaseError:
                raise
            except Exception as e:
                raise DatabaseError(f"未知错误: {str(e)}")
        raise last_exception or DatabaseError("请求失败，请检查网络")

    def _get_col_names(self, sql, cols):
        """缓存列名映射"""
        if sql not in self._col_cache:
            self._col_cache[sql] = [col["name"] for col in cols]
        return self._col_cache[sql]

    def _parse_result(self, data, sql):
        """解析Turso响应，含错误检查和调试输出"""
        try:
            first = data["results"][0]
        except (KeyError, IndexError, TypeError) as e:
            print(f"[TursoDebug] 响应结构异常: keys={list(data.keys()) if isinstance(data,dict) else type(data)}, raw={str(data)[:500]}")
            raise DatabaseError(f"响应结构异常: {e}")
        # 检查SQL错误
        if "error" in first:
            err = first["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            print(f"[TursoDebug] SQL错误: {msg}\n  SQL: {sql[:200]}")
            raise DatabaseError(f"SQL错误: {msg}")
        if "response" not in first:
            print(f"[TursoDebug] 无response键: keys={list(first.keys())}, first={str(first)[:300]}")
            raise DatabaseError(f"响应无response键: {list(first.keys())}")
        resp = first["response"]
        if "error" in resp:
            err = resp["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            print(f"[TursoDebug] 响应错误: {msg}\n  SQL: {sql[:200]}")
            raise DatabaseError(f"响应错误: {msg}")
        return resp.get("result", {})

    @staticmethod
    def _convert_cell(cell):
        """根据Turso返回的type字段转换值类型，避免integer/boolean返回字符串"""
        if isinstance(cell, dict):
            val = cell.get("value")
            ctype = cell.get("type", "").lower()
            if val is None or ctype == "null":
                return None
            if ctype in ("integer", "int", "boolean", "bool"):
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return val
            if ctype in ("real", "float", "double", "decimal", "numeric"):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return val
            return val
        return cell

    def fetch_one(self, sql, params=None):
        try:
            data = self.execute(sql, params)
            result = self._parse_result(data, sql)
            cols = result.get("cols", [])
            rows = result.get("rows", [])
            if not rows:
                return None
            row = rows[0]
            col_names = self._get_col_names(sql, cols)
            record = {}
            for i, col_name in enumerate(col_names):
                record[col_name] = self._convert_cell(row[i])
            return record
        except DatabaseError:
            raise
        except Exception as e:
            print(f"[TursoDebug] 解析异常: {e}, SQL: {sql[:200]}")
            raise DatabaseError(f"解析数据异常: {str(e)}")

    def fetch_all(self, sql, params=None):
        try:
            data = self.execute(sql, params)
            result = self._parse_result(data, sql)
            cols = result.get("cols", [])
            rows = result.get("rows", [])
            col_names = self._get_col_names(sql, cols)
            records = []
            for row in rows:
                record = {}
                for i, col_name in enumerate(col_names):
                    record[col_name] = self._convert_cell(row[i])
                records.append(record)
            return records
        except DatabaseError:
            raise
        except Exception as e:
            print(f"[TursoDebug] 解析异常: {e}, SQL: {sql[:200]}")
            raise DatabaseError(f"解析数据异常: {str(e)}")

    def fetch_many(self, statements):
        """
        批量执行多条SELECT，一次HTTP请求返回多个结果集。
        statements: [(sql, params), ...]
        返回: [ [row_dict, ...], ... ]  与statements一一对应
        """
        self._ensure_config()
        requests_list = []
        for sql, params in statements:
            args = []
            for p in (params or []):
                if p is None:
                    args.append({"type": "null", "value": None})
                else:
                    args.append({"type": "text", "value": str(p)})
            requests_list.append({"type": "execute", "stmt": {"sql": sql, "args": args}})
        requests_list.append({"type": "close"})

        payload = {"requests": requests_list}
        url = self.url.rstrip("/") + "/v2/pipeline"

        last_exception = None
        for attempt in range(3):
            try:
                resp = self._session.post(url, json=payload, timeout=60)
                if resp.status_code != 200:
                    raise DatabaseError(f"批量请求失败 ({resp.status_code}): {resp.text[:200]}")
                data = resp.json()
                break
            except requests.exceptions.RequestException as e:
                last_exception = e
                time.sleep(0.5)
        else:
            raise DatabaseError(f"批量请求失败: {last_exception}")

        # 解析多个结果集
        all_results = []
        raw_results = data.get("results", [])
        for idx, (sql, _) in enumerate(statements):
            try:
                item = raw_results[idx] if idx < len(raw_results) else {}
                if "error" in item:
                    print(f"[TursoDebug] 批量SQL[{idx}]错误: {item['error']} | {sql[:100]}")
                    all_results.append(None)   # None 标记查询失败，调用方应跳过写入
                    continue
                resp_data = item.get("response", {})
                result = resp_data.get("result", {})
                cols = result.get("cols", [])
                rows = result.get("rows", [])
                col_names = [c["name"] for c in cols]
                records = []
                for row in rows:
                    record = {}
                    for i, col_name in enumerate(col_names):
                        record[col_name] = self._convert_cell(row[i])
                    records.append(record)
                all_results.append(records)
            except Exception as e:
                print(f"[TursoDebug] 批量解析[{idx}]失败: {e} | {sql[:100]}")
                all_results.append(None)   # None 标记解析失败
        return all_results



    # ================================================================
    # 用户消息通知
    # ================================================================
    def add_user_message(self, user_id, title, content='', message_type='system'):
        """添加用户消息通知"""
        try:
            self.execute(
                "INSERT INTO user_messages (user_id, title, content, message_type) VALUES (?, ?, ?, ?)",
                (user_id, title, content, message_type)
            )
            return True
        except Exception as e:
            print(f"[user_messages] 添加失败: {e}")
            return False

    def mark_message_read(self, user_id, message_id):
        """标记单条消息为已读"""
        try:
            self.execute(
                "UPDATE user_messages SET is_read = 1, read_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (message_id, user_id)
            )
            return True
        except Exception as e:
            print(f"[user_messages] 标记已读失败: {e}")
            return False

    def mark_all_messages_read(self, user_id):
        """标记所有消息为已读"""
        try:
            self.execute(
                "UPDATE user_messages SET is_read = 1, read_at = CURRENT_TIMESTAMP WHERE user_id = ? AND is_read = 0",
                (user_id,)
            )
            return True
        except Exception as e:
            print(f"[user_messages] 标记全部已读失败: {e}")
            return False
