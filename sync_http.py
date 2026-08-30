# sync_http.py — HTTP拉取云端数据 + UPSERT合并到本地SQLite（批量请求版）
# 优化：1次HTTP请求拉全部表 / 表结构缓存 / 本地索引 / 全量覆盖
import sqlite3
import os
import json
import datetime
import threading
from app_paths import get_app_dir
from database import TursoClient

LOCAL_DB_NAME = "local_cache.db"
SYNC_STATE_FILE = "sync_state.json"
SCHEMA_CACHE_FILE = "schema_cache.json"
SCHEMA_CACHE_TTL_HOURS = 24  # 表结构缓存24小时

# 全量同步表（数据量小，覆盖式）
FULL_TABLES = ["users", "grades", "volumes", "units", "test_config"]

# 时间戳增量同步表: 表名 -> 时间戳字段
INCR_TABLES = {
    "questions": "created_at",
    "words": "updated_at",
    "words_answer_records": "answer_time",
    "user_chinese_culture_answer_history": "answer_time",
    "user_chinese_culture_questions_history": "date",
    "user_chinese_culture_answer_summary": "last_answer_time",
    "chinese_sentences_history": "answer_time",
}

ALL_TABLES = FULL_TABLES + list(INCR_TABLES.keys())

# 本地需要建的索引（加速统计页查询）
LOCAL_INDEXES = [
    ("words_answer_records", "answer_time"),
    ("words_answer_records", "user_id"),
    ("words_answer_records", "word_id"),
    ("words", "unit_id"),
    ("words", "updated_at"),
    ("units", "volume_id"),
    ("volumes", "grade_id"),
    ("questions", "created_at"),
    ("user_chinese_culture_answer_history", "answer_time"),
    ("user_chinese_culture_answer_history", "user_id"),
    ("user_chinese_culture_questions_history", "date"),
    ("user_chinese_culture_answer_summary", "user_id"),
    ("user_chinese_culture_answer_summary", "last_answer_time"),
    ("chinese_sentences_history", "answer_time"),
    ("chinese_sentences_history", "user_id"),
    # 管理后台大表时间索引（加速ORDER BY查询）
    ("score_record", "score_time"),
    ("score_record", "user_id"),
    ("reward_histories", "awarded_at"),
    ("reward_histories", "user_id"),
    ("reward_distribution", "created_at"),
    ("reward_distribution", "user_id"),
    ("item_operation_history", "operation_time"),
    ("item_operation_history", "user_id"),
    ("admin_operation_logs", "operation_time"),
    # 礼包配置与增量同步索引
    ("gift_pack_rules", "gift_item_id"),
    ("gift_pack_rules", "drop_item_id"),
    ("items", "category"),
    # 辞海配置与题库索引
    ("chinese_mode_config", "mode_id"),
    ("materials", "type"),
]

_lock = threading.Lock()


def _local_db_path():
    return str(get_app_dir() / LOCAL_DB_NAME)


def _state_path():
    return str(get_app_dir() / SYNC_STATE_FILE)


def _schema_cache_path():
    return str(get_app_dir() / SCHEMA_CACHE_FILE)


# ---------- 状态 / 缓存 ----------
def _load_state():
    try:
        with open(_state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    try:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def _load_schema_cache():
    """加载表结构缓存，返回 {table: [(name,type,pk),...]} 或 None"""
    try:
        with open(_schema_cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        cached_at = data.get("_cached_at", "")
        if cached_at:
            dt = datetime.datetime.fromisoformat(cached_at)
            if (datetime.datetime.now() - dt).total_seconds() < SCHEMA_CACHE_TTL_HOURS * 3600:
                return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        pass
    return None


def _save_schema_cache(schemas):
    try:
        data = dict(schemas)
        data["_cached_at"] = datetime.datetime.now().isoformat()
        with open(_schema_cache_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


# ---------- 表结构 ----------
def _get_table_schema(turso, table):
    """从云端查询表结构，返回 [(name, type, pk), ...]"""
    rows = turso.fetch_all(f"PRAGMA table_info({table})")
    if not rows:
        return None
    # Turso HTTP API 返回的值都是字符串，pk 必须转 int，否则 "0" 也是 truthy
    return [(r["name"], r["type"], int(r["pk"]) if r["pk"] is not None else 0) for r in rows]


def _get_all_schemas(turso, force_refresh=False):
    """获取所有表结构，优先用缓存，缓存失效时批量请求（1次HTTP拉全部PRAGMA）"""
    if not force_refresh:
        cached = _load_schema_cache()
        if cached and all(t in cached for t in ALL_TABLES):
            print(f"[sync] 表结构使用缓存（{len(cached)}张表）")
            return cached
    print(f"[sync] 批量获取 {len(ALL_TABLES)} 张表结构...")
    # 批量PRAGMA查询，1次HTTP请求
    statements = [(f"PRAGMA table_info({t})", []) for t in ALL_TABLES]
    try:
        results = turso.fetch_many(statements)
    except Exception as e:
        print(f"[sync] 批量获取表结构失败: {e}，降级为逐个查询")
        results = None
    schemas = {}
    if results:
        for idx, t in enumerate(ALL_TABLES):
            rows = results[idx] if idx < len(results) else None
            if rows:
                schemas[t] = [(r["name"], r["type"], int(r["pk"]) if r["pk"] is not None else 0) for r in rows]
    else:
        # 降级：逐个查询
        for t in ALL_TABLES:
            s = _get_table_schema(turso, t)
            if s:
                schemas[t] = s
    if schemas:
        _save_schema_cache(schemas)
    print(f"[sync] 获取到 {len(schemas)}/{len(ALL_TABLES)} 张表结构")
    return schemas


# ---------- 建表 / 索引 ----------
def _create_table_local(conn, table, schema):
    """建表 + 缺列自动ADD COLUMN（正确处理复合主键）"""
    cols = []
    pk_cols = [name for name, ctype, pk in schema if pk]
    for name, ctype, pk in schema:
        col_def = f'"{name}" {ctype}'
        # 单列主键才在列定义里加 PRIMARY KEY；复合主键用表级约束
        if pk and len(pk_cols) == 1:
            col_def += " PRIMARY KEY"
        cols.append(col_def)
    # 复合主键：加表级 PRIMARY KEY 约束
    if len(pk_cols) > 1:
        pk_str = ", ".join([f'"{c}"' for c in pk_cols])
        cols.append(f"PRIMARY KEY ({pk_str})")
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(cols)})')
    # 对齐缺列
    try:
        local_cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
        for name, ctype, pk in schema:
            if name not in local_cols and not pk:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ctype}')
                print(f"[sync] {table}: 新增列 {name}")
    except Exception as e:
        print(f"[sync] {table}: 表结构对齐失败: {e}")


def _ensure_local_indexes(conn):
    """创建本地索引（加速统计查询），已存在则跳过"""
    for table, col in LOCAL_INDEXES:
        idx_name = f"idx_{table}_{col}"
        try:
            conn.execute(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table}"("{col}")')
        except Exception:
            pass
    conn.commit()


# ---------- UPSERT ----------
def _upsert_rows(conn, table, rows, schema):
    if not rows or not schema:
        return 0
    col_names = [s[0] for s in schema]
    placeholders = ",".join(["?"] * len(col_names))
    col_str = ",".join([f'"{c}"' for c in col_names])
    sql = f'INSERT OR REPLACE INTO "{table}" ({col_str}) VALUES ({placeholders})'
    batch = [[row.get(c) for c in col_names] for row in rows]
    conn.executemany(sql, batch)
    conn.commit()
    return len(rows)


def _replace_rows(conn, table, rows, schema):
    """覆盖式写入：先DELETE全表，再INSERT（用于全量小表）
    安全保护：云端返回空列表但本地有数据时，不DELETE，保留旧数据防止误删。
    """
    if not schema:
        return 0
    # 安全保护：空结果时检查本地是否有数据，防止查询异常导致误删
    if not rows:
        try:
            local_cnt = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        except Exception:
            local_cnt = 0
        if local_cnt > 0:
            print(f"[sync][WARN] {table}: 云端返回0行但本地有{local_cnt}行，疑似查询异常，保留本地数据不覆盖")
            return 0
        # 本地也为空，无需DELETE
        return 0
    conn.execute(f'DELETE FROM "{table}"')
    return _upsert_rows(conn, table, rows, schema)


# ---------- 云端字段迁移（一次性） ----------
_cloud_migrated = False

def migrate_cloud_add_sync_enabled():
    """在云端users表添加sync_enabled字段（一次性，幂等）"""
    global _cloud_migrated
    if _cloud_migrated:
        return True
    try:
        from database import TursoClient
        turso = TursoClient()
        # 先检查字段是否已存在
        cols = turso.fetch_all("PRAGMA table_info(users)") or []
        has_col = any(c.get('name') == 'sync_enabled' for c in cols)
        if not has_col:
            turso.execute("ALTER TABLE users ADD COLUMN sync_enabled INTEGER DEFAULT 1")
            print("[sync] 云端users表已添加 sync_enabled 字段")
        _cloud_migrated = True
        return True
    except Exception as e:
        print(f"[sync] 云端迁移失败: {e}")
        return False


def ensure_local_sync_enabled_column():
    """确保本地users表有sync_enabled字段（从云端同步后应该已有，这里做兜底）"""
    try:
        conn = sqlite3.connect(_local_db_path())
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "sync_enabled" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN sync_enabled INTEGER DEFAULT 1")
            conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[sync] ensure_local_sync_enabled_column fail: {e}")
        return False


def get_user_sync_enabled(user_id):
    """查询用户是否开启登录同步（从本地读取，默认开启）"""
    try:
        ensure_local_sync_enabled_column()
        conn = sqlite3.connect(_local_db_path())
        row = conn.execute("SELECT sync_enabled FROM users WHERE user_id=?", [user_id]).fetchone()
        conn.close()
        if row is None:
            return True
        return bool(row[0]) if row[0] is not None else True
    except Exception:
        return True


# ---------- 主同步 ----------
def sync_to_local(timeout=120, force_refresh_schema=False):
    """
    同步云端数据到本地SQLite（批量请求版）
    - 1次HTTP请求拉取全部10张表
    - 表结构缓存（减少PRAGMA请求）
    - 全量小表覆盖式（DELETE+INSERT）
    - 自动建本地索引
    - 查询失败的表跳过写入，保留旧数据
    """
    print("[sync] === 开始同步 ===")
    with _lock:
        conn = None
        try:
            print("[sync] 步骤1: 云端字段迁移检查...")
            migrate_cloud_add_sync_enabled()
            print("[sync] 步骤2: 本地表结构检查...")
            ensure_local_sync_enabled_column()
            turso = TursoClient()
            conn = sqlite3.connect(_local_db_path())
            state = _load_state()
            last_sync = state.get("last_sync", "2000-01-01 00:00:00")
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[sync] 上次同步: {last_sync}")

            # 1. 获取表结构（缓存优先）
            print("[sync] 步骤3: 获取表结构...")
            schemas = _get_all_schemas(turso, force_refresh=force_refresh_schema)
            if not schemas:
                return False, "无法获取表结构"

            # 2. 建表
            for table in ALL_TABLES:
                if table in schemas:
                    _create_table_local(conn, table, schemas[table])

            # 3. 构建批量SQL（1次请求拉全部表）
            statements = []
            table_order = []
            for table in FULL_TABLES:
                statements.append((f'SELECT * FROM "{table}"', []))
                table_order.append((table, False))
            for table, ts_field in INCR_TABLES.items():
                if last_sync == "2000-01-01 00:00:00":
                    # 首次同步：全量
                    statements.append((f'SELECT * FROM "{table}"', []))
                    table_order.append((table, False))
                else:
                    # 增量：检查字段是否存在
                    schema = schemas.get(table, [])
                    col_names = [s[0] for s in schema]
                    if ts_field in col_names:
                        statements.append((f'SELECT * FROM "{table}" WHERE "{ts_field}" > ? ORDER BY "{ts_field}"', [last_sync]))
                        table_order.append((table, True))
                    else:
                        statements.append((f'SELECT * FROM "{table}"', []))
                        table_order.append((table, False))

            # 4. 单次批量请求
            print(f"[sync] 批量请求 {len(statements)} 张表...")
            all_rows = turso.fetch_many(statements)

            # 5. 串行写入（查询失败的表跳过，保留旧数据）
            total = 0
            for idx, (table, is_incr) in enumerate(table_order):
                rows = all_rows[idx] if idx < len(all_rows) else None
                if rows is None:
                    print(f"[sync] {table}: 查询失败，跳过写入（保留旧数据）")
                    continue
                schema = schemas.get(table)
                if not schema:
                    continue
                if table in FULL_TABLES:
                    cnt = _replace_rows(conn, table, rows, schema)
                    print(f"[sync] {table}: {cnt} 行 (全量覆盖)")
                else:
                    cnt = _upsert_rows(conn, table, rows, schema)
                    mode = "增量" if is_incr else "全量"
                    print(f"[sync] {table}: {cnt} 行 ({mode})")
                total += cnt

            # 6. 建本地索引
            _ensure_local_indexes(conn)

            state["last_sync"] = now_str
            _save_state(state)
            return True, f"同步完成，共写入 {total} 行（1次请求）"
        except Exception as e:
            return False, f"同步失败: {e}"
        finally:
            if conn is not None:
                conn.close()


def force_full_sync(timeout=120):
    """强制全量同步（忽略增量时间戳，刷新表结构缓存，批量请求）"""
    with _lock:
        conn = None
        try:
            turso = TursoClient()
            conn = sqlite3.connect(_local_db_path())
            schemas = _get_all_schemas(turso, force_refresh=True)

            statements = [(f'SELECT * FROM "{t}"', []) for t in ALL_TABLES]
            all_rows = turso.fetch_many(statements)

            total = 0
            for idx, table in enumerate(ALL_TABLES):
                if table not in schemas:
                    continue
                rows = all_rows[idx] if idx < len(all_rows) else None
                if rows is None:
                    print(f"[sync-full] {table}: 查询失败，跳过")
                    continue
                _create_table_local(conn, table, schemas[table])
                cnt = _replace_rows(conn, table, rows, schemas[table])
                total += cnt
                print(f"[sync-full] {table}: {cnt} 行")

            _ensure_local_indexes(conn)
            state = _load_state()
            state["last_sync"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _save_state(state)
            return True, f"全量同步完成，共写入 {total} 行（1次请求）"
        except Exception as e:
            return False, f"全量同步失败: {e}"
        finally:
            if conn is not None:
                conn.close()


class LocalSQLiteDB:
    """本地SQLite查询，兼容 TursoClient.fetch_all/fetch_one 接口"""

    _conn_cache = {}
    _conn_mtime = {}

    def __init__(self):
        self.db_path = _local_db_path()

    @property
    def available(self):
        return os.path.exists(self.db_path)

    def _conn(self):
        # 检测文件是否被替换（mtime 变化 → 清除旧连接）
        try:
            mtime = os.path.getmtime(self.db_path)
        except OSError:
            mtime = 0
        cached_mtime = LocalSQLiteDB._conn_mtime.get(self.db_path)
        if self.db_path in LocalSQLiteDB._conn_cache and cached_mtime != mtime:
            try:
                LocalSQLiteDB._conn_cache[self.db_path].close()
            except Exception:
                pass
            del LocalSQLiteDB._conn_cache[self.db_path]
            LocalSQLiteDB._conn_mtime.pop(self.db_path, None)

        if self.db_path not in LocalSQLiteDB._conn_cache:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            LocalSQLiteDB._conn_cache[self.db_path] = conn
            LocalSQLiteDB._conn_mtime[self.db_path] = mtime
        return LocalSQLiteDB._conn_cache[self.db_path]

    def fetch_all(self, sql, params=None):
        if not self.available:
            return []
        try:
            conn = self._conn()
            cur = conn.execute(sql, params or [])
            rows = [dict(r) for r in cur.fetchall()]
            return rows
        except Exception as e:
            print(f"[LocalSQLiteDB] fetch_all 失败: {e} | SQL: {sql[:120]}")
            return []

    def fetch_one(self, sql, params=None):
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None
