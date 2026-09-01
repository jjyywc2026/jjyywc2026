# pages/admin/users.py
import flet as ft
import hashlib
from .base import AdminBaseTab

# 账户状态映射（与登录验证一致）
STATUS_MAP = {0: '正常', 1: '禁用', 2: '冻结', 3: '封禁', 4: '注销中', 5: '已注销'}
STATUS_COLORS = {0: ft.Colors.GREEN_600, 1: ft.Colors.RED_500, 2: ft.Colors.ORANGE_500,
                 3: ft.Colors.RED_700, 4: ft.Colors.GREY_500, 5: ft.Colors.GREY_400}


def _status_name(val):
    """云端返回字符串，统一转int后查映射"""
    try:
        v = int(val) if val is not None else 0
    except (ValueError, TypeError):
        v = 0
    return STATUS_MAP.get(v, f'状态{v}')


def _status_color(val):
    try:
        v = int(val) if val is not None else 0
    except (ValueError, TypeError):
        v = 0
    return STATUS_COLORS.get(v, ft.Colors.GREY_500)


class UserManagementTab(AdminBaseTab):
    """用户管理：列表 → 点击查看详情 → 编辑/重置密码/修改密码/变更状态/删除"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._search_tf = None

    def build(self):
        search_row, self._search_tf = self._search_bar("搜索用户", "用户名或ID", self._do_search)
        add_btn = ft.IconButton(
            ft.Icons.PERSON_ADD, icon_size=22, tooltip="添加用户",
            on_click=self._add_user,
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 padding=ft.padding.all(8)),
        )
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([
            ft.Row([ft.Container(content=search_row, expand=True), add_btn],
                   spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self._list_view,
        ], spacing=4, expand=True)

    async def load_data(self):
        await self._load_users()

    def _do_search(self, keyword):
        self._search_loading_show(True)
        self.page.run_task(self._load_users, keyword)

    async def _load_users(self, keyword=None):
        import asyncio
        import datetime
        await asyncio.sleep(0.05)

        def _query_all():
            # 2条SQL合并为1次批量请求
            if keyword and keyword.strip():
                kw = f"%{keyword.strip()}%"
                user_sql = ("SELECT * FROM users WHERE username LIKE ? OR CAST(user_id AS TEXT) LIKE ? ORDER BY user_id", [kw, kw])
            else:
                user_sql = ("SELECT * FROM users ORDER BY user_id", [])
            sess_sql = ("SELECT user_id, last_heartbeat, login_time, is_active FROM user_sessions ORDER BY last_heartbeat DESC", [])
            try:
                results = self.db.fetch_many([user_sql, sess_sql])
            except Exception as e:
                return None, None, str(e)
            def _safe(idx):
                r = results[idx] if idx < len(results) else []
                return r if r is not None else []
            return _safe(0), _safe(1), None

        rows, sess_rows, err = await asyncio.to_thread(_query_all)
        if err:
            self.snack(f"加载用户失败: {err}")
            self._search_loading_show(False)
            return

        # 2. 处理会话数据（判断在线状态）
        session_map = {}
        now = datetime.datetime.now()
        for s in sess_rows or []:
            uid = str(s.get('user_id'))
            if uid in session_map:
                continue  # 只保留最新一条
            hb = s.get('last_heartbeat')
            hb_time = None
            if hb:
                try:
                    hb_time = datetime.datetime.strptime(str(hb)[:19], '%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
            is_online = bool(s.get('is_active')) and hb_time and (now - hb_time).total_seconds() <= 300
            session_map[uid] = {'hb': hb, 'hb_time': hb_time, 'is_active': s.get('is_active'), 'online': is_online}

        online_count = sum(1 for v in session_map.values() if v.get('online'))

        def _fmt_active(uid_str):
            sinfo = session_map.get(uid_str)
            if not sinfo:
                return None
            hb_time = sinfo.get('hb_time')
            if not hb_time:
                return None
            diff = (now - hb_time).total_seconds()
            if diff < 60:
                return "刚刚"
            elif diff < 3600:
                return f"{int(diff/60)}分钟前"
            elif diff < 86400:
                return f"{int(diff/3600)}小时前"
            else:
                return f"{int(diff/86400)}天前"

        tiles = []
        # 顶部统计条
        tiles.append(ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Row([
                        ft.Container(width=8, height=8, border_radius=4, bgcolor=ft.Colors.GREEN_500),
                        ft.Text(f"在线 {online_count}人", size=11, color=ft.Colors.GREEN_700, weight=ft.FontWeight.BOLD),
                    ], spacing=4),
                    bgcolor="#E8F5E9", border_radius=12,
                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                ),
                ft.Text(f"共 {len(rows or [])} 个用户", size=11, color=ft.Colors.GREY_500),
            ], spacing=8),
            padding=ft.padding.symmetric(vertical=4),
        ))

        for r in rows or []:
            uid = r['user_id']
            uid_str = str(uid)
            st = _status_name(r.get('user_status'))
            st_color = _status_color(r.get('user_status'))
            sinfo = session_map.get(uid_str, {})
            is_online = sinfo.get('online', False)
            active_text = _fmt_active(uid_str)

            # 头像 + 在线圆点
            dot_color = ft.Colors.GREEN_500 if is_online else ft.Colors.GREY_400
            avatar = ft.Stack([
                ft.CircleAvatar(content=ft.Text((r.get('username') or '?')[0], size=12),
                                bgcolor=ft.Colors.BLUE_100 if not is_online else ft.Colors.GREEN_100,
                                color=ft.Colors.BLUE_800, radius=18),
                ft.Container(
                    content=ft.Container(width=9, height=9, border_radius=5,
                                         bgcolor=dot_color, border=ft.border.all(2, ft.Colors.WHITE)),
                    alignment=ft.alignment.bottom_right,
                ),
            ], width=36, height=36)

            # 标题：用户名 + 在线徽章
            title_children = [ft.Text(f"{r.get('username','?')} (ID:{uid})", size=12,
                                      weight=ft.FontWeight.W_700 if is_online else ft.FontWeight.NORMAL)]
            if is_online:
                title_children.append(ft.Container(
                    content=ft.Text("在线", size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor=ft.Colors.GREEN_500, border_radius=6,
                    padding=ft.padding.symmetric(horizontal=5, vertical=1),
                ))
            title_row = ft.Row(title_children, spacing=6)

            # 副标题：等级积分 + 活跃时间 + 状态
            sub_parts = [f"Lv.{r.get('level_id',1)}", f"{r.get('score',0)}分", st]
            if active_text:
                sub_parts.insert(2, f"活跃:{active_text}")
            subtitle = ft.Text(" · ".join(sub_parts), size=10,
                               color=ft.Colors.GREEN_800 if is_online else st_color)

            tiles.append(self._list_tile(
                avatar,
                title_row,
                subtitle,
                trailing=ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14,
                                 color=ft.Colors.GREEN_400 if is_online else ft.Colors.GREY_400),
                on_click=lambda e, u=r, online=is_online: self._show_user_detail(u, online),
                bgcolor="#E8F5E9" if is_online else None,
            ))
        if not rows:
            tiles.append(self._empty("暂无用户"))
        self._list_view.controls = tiles
        self._search_loading_show(False)
        self.page.update()

    # ---------- 用户详情（全部字段） ----------
    def _show_user_detail(self, user, is_online=False):
        st = _status_name(user.get('user_status'))
        st_color = _status_color(user.get('user_status'))

        # 从user_sessions查询最后登录时间
        last_login = '-'
        try:
            row = self.db.fetch_one(
                "SELECT login_time FROM user_sessions WHERE user_id=? ORDER BY login_time DESC LIMIT 1",
                [user['user_id']])
            if row and row.get('login_time'):
                last_login = str(row['login_time'])[:19]
        except Exception:
            last_login = user.get('last_login_date', '-')

        # 在线状态标识
        online_badge = ft.Container()
        if is_online:
            online_badge = ft.Container(
                content=ft.Row([
                    ft.Container(width=8, height=8, border_radius=4, bgcolor=ft.Colors.WHITE),
                    ft.Text("在线", size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=ft.Colors.GREEN_500, border_radius=10,
                padding=ft.padding.symmetric(horizontal=10, vertical=3),
            )

        # 全部字段展示
        info_items = [
            ("用户ID", str(user['user_id'])),
            ("用户名", user.get('username', '-')),
            ("用户类型", user.get('user_type', '-')),
            ("在线状态", "在线" if is_online else "离线"),
            ("等级", f"Lv.{user.get('level_id', 1)}"),
            ("积分", str(user.get('score', 0))),
            ("总积分", str(user.get('total_points', 0))),
            ("星星", str(user.get('total_stars', 0))),
            ("经验", str(user.get('experience', 0))),
            ("评分开关", str(user.get('evaluation_score', 0))),
            ("平均评测分", str(user.get('avg_evaluation_score', 0))),
            ("总使用时长", f"{user.get('total_time', 0)}分钟"),
            ("学习时长", user.get('studay_time', '-')),
            ("注册日期", user.get('reg_date', '-')),
            ("连续登录", f"{user.get('consecutive_login_days', 0)}天"),
            ("最后登录", last_login),
            ("账户状态", st),
        ]
        info_rows = []
        for label, val in info_items:
            if label == '账户状态':
                c = st_color
            elif label == '在线状态':
                c = ft.Colors.GREEN_600 if is_online else ft.Colors.GREY_500
            else:
                c = ft.Colors.BLUE_800
            info_rows.append(ft.Row([
                ft.Text(f"{label}:", size=11, color=ft.Colors.GREY_500, width=80),
                ft.Text(str(val), size=11, weight=ft.FontWeight.W_600, color=c, no_wrap=True),
            ], spacing=4))

        actions = ft.Column([
            ft.Row([
                self._mini_btn("编辑", ft.Icons.EDIT, ft.Colors.BLUE_600,
                               lambda e: self._edit_user(user)),
                self._mini_btn("登录记录", ft.Icons.HISTORY, ft.Colors.CYAN_700,
                               lambda e: self._show_login_history(user)),
                self._mini_btn("重置密码", ft.Icons.LOCK_RESET, ft.Colors.ORANGE_600,
                               lambda e: self._reset_password(user)),
            ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([
                self._mini_btn("修改密码", ft.Icons.PASSWORD, ft.Colors.TEAL_600,
                               lambda e: self._change_password(user)),
                self._mini_btn("变更状态", ft.Icons.SECURITY, ft.Colors.PURPLE_600,
                               lambda e: self._change_status(user)),
                self._mini_btn("删除", ft.Icons.DELETE, ft.Colors.RED_500,
                               lambda e: self._delete_user(user)),
            ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([
                self._mini_btn("重置二级密码", ft.Icons.LOCK_RESET, ft.Colors.DEEP_ORANGE_600,
                               lambda e: self._reset_out_password(user)),
                self._mini_btn("修改二级密码", ft.Icons.PASSWORD, ft.Colors.INDIGO_600,
                               lambda e: self._change_out_password(user)),
            ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=4, tight=True)

        # 登录同步开关（直接用云端返回的sync_enabled，用户列表是SELECT *）
        try:
            sync_on = bool(int(user.get('sync_enabled', 1)))
        except (ValueError, TypeError):
            sync_on = True
        sync_status = {"ref": None}

        def _on_sync_change(e):
            new_val = e.control.value
            self._toggle_user_sync(user, new_val)
            if sync_status["ref"]:
                sync_status["ref"].value = "已开启" if new_val else "已关闭"
                sync_status["ref"].color = ft.Colors.GREEN_700 if new_val else ft.Colors.GREY_500
                try:
                    sync_status["ref"].update()
                except Exception:
                    pass

        sync_switch = ft.Switch(
            value=sync_on,
            active_color=ft.Colors.GREEN_600,
            active_track_color=ft.Colors.GREEN_200,
            on_change=_on_sync_change,
        )
        sync_status["ref"] = ft.Text(
            "已开启" if sync_on else "已关闭",
            size=10, color=ft.Colors.GREEN_700 if sync_on else ft.Colors.GREY_500,
            weight=ft.FontWeight.W_600,
        )
        sync_card = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CLOUD_SYNC, size=14,
                        color=ft.Colors.BLUE_700 if sync_on else ft.Colors.GREY_500),
                ft.Text("登录同步", size=11, weight=ft.FontWeight.W_600,
                        color=ft.Colors.GREY_800, expand=True),
                sync_status["ref"],
                sync_switch,
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=ft.Colors.BLUE_50, border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=2),
        )

        content = ft.Column([
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, icon_size=20, icon_color=ft.Colors.BLUE_700,
                              on_click=lambda e: self._close_dialog(dlg),
                              style=ft.ButtonStyle(padding=ft.padding.all(4))),
                ft.Text(f"用户详情 - {user.get('username','')}", size=15,
                        weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800, expand=True),
                online_badge,
            ], spacing=4, alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1, color=ft.Colors.GREY_200),
            ft.Column(info_rows, spacing=2, tight=True),
            ft.Container(height=6),
            sync_card,
            ft.Container(height=6),
            ft.Text("操作", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_700),
            actions,
        ], spacing=4, tight=True, scroll=ft.ScrollMode.ADAPTIVE)

        dlg = ft.AlertDialog(
            content=ft.Container(content=content, width=380, padding=ft.padding.only(top=6, left=10, right=10, bottom=10)),
        )
        self.page.open(dlg)

    def _toggle_user_sync(self, user, enabled):
        """切换用户登录同步开关（写入云端 + 更新本地缓存 + 更新内存对象）"""
        uid = user.get('user_id')
        uname = user.get('username', '')

        def do_save():
            self.db.execute("UPDATE users SET sync_enabled=? WHERE user_id=?",
                            [1 if enabled else 0, uid])
            try:
                import sqlite3
                from sync_http import _local_db_path, ensure_local_sync_enabled_column
                ensure_local_sync_enabled_column()
                conn = sqlite3.connect(_local_db_path())
                conn.execute("UPDATE users SET sync_enabled=? WHERE user_id=?",
                             [1 if enabled else 0, uid])
                conn.commit()
                conn.close()
            except Exception:
                pass
            user['sync_enabled'] = 1 if enabled else 0
            self._log_operation("edit_user_sync", "user", target_id=uid,
                                target_name=uname,
                                details=f"同步开关:{'开启' if enabled else '关闭'}",
                                before_state={'sync_enabled': user.get('sync_enabled', 0)},
                                after_state={'sync_enabled': 1 if enabled else 0})

        self.run_save_async(do_save,
                            success_msg=f"已{'开启' if enabled else '关闭'} {uname} 的登录同步",
                            confirm_msg=f"确定要{'开启' if enabled else '关闭'} {uname} 的登录同步吗？")

    # ---------- 登录记录 ----------
    def _show_login_history(self, user):
        uid = user['user_id']
        uname = user.get('username', '?')
        try:
            rows = self.db.fetch_all(
                "SELECT id, device_id, login_time, last_heartbeat, logout_time, is_active FROM user_sessions WHERE user_id=? ORDER BY login_time DESC LIMIT 50",
                [uid])
        except Exception as e:
            self.snack(f"查询失败: {e}")
            return

        import datetime
        now = datetime.datetime.now()

        def _parse_dt(s):
            if not s:
                return None
            try:
                return datetime.datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

        def _fmt_duration(start, end):
            if not start:
                return "—"
            if not end:
                end = now
            delta = end - start
            mins = int(delta.total_seconds() // 60)
            if mins < 60:
                return f"{mins}分钟"
            hours = mins // 60
            rem = mins % 60
            return f"{hours}小时{rem}分" if rem else f"{hours}小时"

        def _judge_status(r):
            """判断会话状态：在线/已退出/异常掉线"""
            is_active = int(r.get('is_active', 0) or 0)
            logout = r.get('logout_time')
            hb = _parse_dt(r.get('last_heartbeat'))
            # 有退出时间 → 已退出
            if logout:
                return "已退出", ft.Colors.GREY_500, ft.Colors.GREY_100
            # is_active=0 但无退出时间 → 异常退出
            if not is_active:
                return "异常退出", ft.Colors.ORANGE_600, ft.Colors.ORANGE_50
            # is_active=1 且心跳在5分钟内 → 在线
            if hb and (now - hb).total_seconds() < 300:
                return "在线", ft.Colors.GREEN_600, ft.Colors.GREEN_50
            # is_active=1 但心跳超过5分钟 → 掉线（未正常退出）
            return "掉线", ft.Colors.RED_500, ft.Colors.RED_50

        tiles = []
        online_count = 0
        for r in rows or []:
            status_text, status_color, status_bg = _judge_status(r)
            if status_text == "在线":
                online_count += 1
            login = str(r.get('login_time', ''))[:19] or "—"
            hb = str(r.get('last_heartbeat', ''))[:19] or "—"
            logout = str(r.get('logout_time', ''))[:19] if r.get('logout_time') else "未退出"
            device_raw = str(r.get('device_id', '')) or ""
            device = device_raw[:8] + "…" if len(device_raw) > 8 else (device_raw or "未知设备")

            login_dt = _parse_dt(r.get('login_time'))
            logout_dt = _parse_dt(r.get('logout_time'))
            hb_dt = _parse_dt(r.get('last_heartbeat'))
            is_active = int(r.get('is_active', 0) or 0)
            # 时长计算：有退出时间用退出时间；在线用当前时间；异常/掉线用心跳时间
            if logout_dt:
                end_dt = logout_dt
            elif is_active and status_text == "在线":
                end_dt = now
            elif hb_dt:
                end_dt = hb_dt
            else:
                end_dt = now
            duration = _fmt_duration(login_dt, end_dt)

            tiles.append(ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(
                            content=ft.Text(status_text, size=10, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=status_color, border_radius=4,
                            padding=ft.padding.symmetric(horizontal=6, vertical=2)),
                        ft.Text(login, size=12, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_800),
                        ft.Container(expand=True),
                        ft.Text(f"时长 {duration}", size=10, color=ft.Colors.GREY_600),
                    ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        ft.Text(f"设备: {device}", size=10, color=ft.Colors.GREY_500),
                        ft.Container(width=8),
                        ft.Text(f"心跳: {hb}", size=10, color=ft.Colors.GREY_500),
                    ], spacing=0),
                    ft.Text(f"退出: {logout}", size=10, color=ft.Colors.GREY_500),
                ], spacing=2, tight=True),
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                bgcolor=status_bg, border_radius=6,
                border=ft.border.all(0.5, ft.Colors.GREY_200),
                margin=ft.margin.only(bottom=3),
            ))
        if not tiles:
            tiles.append(self._empty("暂无登录记录"))

        content = ft.Column([
            ft.Row([
                ft.Text(f"登录记录 - {uname}", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Text(f"在线 {online_count}", size=10, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor=ft.Colors.GREEN_500, border_radius=8,
                    padding=ft.padding.symmetric(horizontal=8, vertical=2)),
            ], spacing=4),
            ft.Text(f"共 {len(rows or [])} 条记录 · 最近50条", size=11, color=ft.Colors.GREY_500),
            ft.Divider(height=1, color=ft.Colors.GREY_200),
            ft.ListView(controls=tiles, spacing=0, expand=True),
        ], spacing=6, tight=False, expand=True, height=500)

        dlg = ft.AlertDialog(
            content=ft.Container(content=content, width=400, padding=4),
            actions=[ft.TextButton("关闭", on_click=lambda e: self._close_dialog(dlg))],
        )
        self.page.open(dlg)

    def _mini_btn(self, text, icon, color, on_click):
        return ft.ElevatedButton(
            text, icon=icon, on_click=on_click,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
                bgcolor=color, color=ft.Colors.WHITE, elevation=1,
                padding=ft.padding.symmetric(horizontal=8, vertical=6),
                text_style=ft.TextStyle(size=10),
            ))

    # ---------- 添加用户 ----------
    def _add_user(self, e=None):
        fields = [
            ("用户名", "username", "", "text"),
            ("密码", "password", "", "text"),
            ("用户类型", "user_type", "user", ["user", "admin"]),
        ]
        def on_submit(data):
            try:
                uname = data['username'].strip()
                pwd = data['password'].strip()
                if not uname or not pwd:
                    self.snack("用户名和密码不能为空")
                    return
                h1 = hashlib.md5(pwd.encode()).hexdigest()
                hashed = hashlib.md5(h1.encode()).hexdigest()
                self.db.execute(
                    "INSERT INTO users (username, password, user_type, score, level_id, total_stars, experience, user_status) VALUES (?,?,?,?,?,?,?,?)",
                    [uname, hashed, data['user_type'], 0, 1, 0, 0, 0])
                self._log_operation("add_user", "user", target_name=uname,
                                    details=f"类型:{data['user_type']}",
                                    after_state={'username': uname, 'user_type': data['user_type']})
                self.snack(f"已添加用户: {uname}")
                self.page.run_task(self._load_users)
            except Exception as ex:
                self.snack(f"添加失败: {ex}")
        self.form_dialog("添加用户", fields, on_submit, submit_text="添加")

    # ---------- 编辑用户（等级/积分/经验/星星只读显示，密码不可编辑） ----------
    def _edit_user(self, user):
        # 只读字段用text显示，可编辑字段用输入框
        readonly_info = ft.Container(
            content=ft.Column([
                ft.Text(f"等级: Lv.{user.get('level_id',1)}  |  积分: {user.get('score',0)}  |  经验: {user.get('experience',0)}  |  星星: {user.get('total_stars',0)}",
                        size=11, color=ft.Colors.GREY_600),
                ft.Text(f"平均评测分: {user.get('avg_evaluation_score', 0)}  |  总积分: {user.get('total_points', 0)}  |  连续登录: {user.get('consecutive_login_days', 0)}天",
                        size=11, color=ft.Colors.GREY_600),
                ft.Text("（等级/积分/经验/星星/平均评测分/总积分/连续登录为系统计算字段，不可手动编辑）", size=9, color=ft.Colors.GREY_400),
            ], spacing=2),
            bgcolor=ft.Colors.GREY_50, border_radius=6, padding=8, margin=ft.margin.only(bottom=8))

        fields = [
            ("用户名", "username", user.get('username'), "text"),
            ("用户类型", "user_type", user.get('user_type'), ["user", "admin"]),
            ("总使用时长(分钟)", "total_time", user.get('total_time', 0), "number"),
            ("学习时长", "studay_time", user.get('studay_time', ''), "text"),
            ("评分开关", "evaluation_score", user.get('evaluation_score', 0), "number"),
        ]

        def on_submit(data):
            try:
                self.db.execute(
                    """UPDATE users SET username=?, user_type=?, total_time=?, studay_time=?,
                       evaluation_score=?
                       WHERE user_id=?""",
                    [data['username'], data['user_type'],
                     int(data['total_time'] or 0), data['studay_time'] or '',
                     int(data['evaluation_score'] or 0),
                     user['user_id']])
                before = {'username': user.get('username'), 'user_type': user.get('user_type'),
                          'total_time': user.get('total_time', 0), 'studay_time': user.get('studay_time', ''),
                          'evaluation_score': user.get('evaluation_score', 0)}
                after = {'username': data['username'], 'user_type': data['user_type'],
                         'total_time': int(data['total_time'] or 0), 'studay_time': data['studay_time'] or '',
                         'evaluation_score': int(data['evaluation_score'] or 0)}
                self._log_operation("edit_user", "user", target_id=user['user_id'],
                                    target_name=data['username'],
                                    details=f"类型:{data['user_type']},时长:{data['total_time']}",
                                    before_state=before, after_state=after)
                self.snack(f"已更新: {data['username']}")
                self.page.run_task(self._load_users)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        # 自定义表单：只读信息 + 可编辑字段
        refs = {}
        controls = [readonly_info]
        for label, key, initial, ftype in fields:
            tf = ft.TextField(label=label, value=str(initial or ''),
                              border_radius=8, expand=True)
            refs[key] = tf
            controls.append(tf)

        def do_submit(e):
            data = {k: c.value for k, c in refs.items()}
            dlg.open = False
            self._close_dialog(dlg)
            on_submit(data)

        dlg = ft.AlertDialog(
            title=ft.Text(f"编辑用户 {user.get('username','')}", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column(controls, spacing=8, scroll=ft.ScrollMode.ADAPTIVE),
                                 width=400, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_submit,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)

    # ---------- 重置密码 ----------
    def _reset_password(self, user):
        default_pwd = "123456"
        self.confirm_and_run(
            "重置密码", f"确定将「{user.get('username','')}」的密码重置为 {default_pwd} 吗？",
            self._do_reset_password, user['user_id'], default_pwd,
            success_msg=f"密码已重置为 {default_pwd}", loading_msg="重置中...")

    async def _do_reset_password(self, user_id, new_pwd):
        h1 = hashlib.md5(new_pwd.encode()).hexdigest()
        hashed = hashlib.md5(h1.encode()).hexdigest()
        self.db.execute("UPDATE users SET password=? WHERE user_id=?", [hashed, user_id])
        self._log_operation("reset_password", "user", target_id=user_id, details="重置为123456")
        admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
        self.db.add_user_message(user_id, '登录密码已重置', f'{admin_name} 将你的登录密码重置为 123456\n为了账户安全，请登录后尽快修改密码', 'system')
        await self._load_users()

    # ---------- 修改密码 ----------
    def _change_password(self, user):
        fields = [
            ("新密码", "new_pwd", "", "text"),
            ("确认密码", "confirm_pwd", "", "text"),
        ]
        def on_submit(data):
            pwd = data['new_pwd'].strip()
            confirm = data['confirm_pwd'].strip()
            if len(pwd) < 6 or len(pwd) > 20:
                self.snack("密码长度需6-20位")
                return
            if ' ' in pwd:
                self.snack("密码不能包含空格")
                return
            import re
            if not re.match(r'^[a-zA-Z0-9]+$', pwd):
                self.snack("密码只能包含英文字母和数字，不能使用特殊字符")
                return
            if not any(c.isalpha() for c in pwd):
                self.snack("密码必须包含字母")
                return
            if not any(c.isdigit() for c in pwd):
                self.snack("密码必须包含数字")
                return
            if pwd != confirm:
                self.snack("两次密码不一致")
                return
            self.confirm_and_run(
                "修改密码", f"确定修改「{user.get('username','')}」的密码吗？",
                self._do_change_password, user['user_id'], pwd,
                success_msg="密码修改成功", loading_msg="修改中...")
        self.form_dialog(f"修改密码 - {user.get('username','')}", fields, on_submit)

    async def _do_change_password(self, user_id, new_pwd):
        h1 = hashlib.md5(new_pwd.encode()).hexdigest()
        hashed = hashlib.md5(h1.encode()).hexdigest()
        self.db.execute("UPDATE users SET password=? WHERE user_id=?", [hashed, user_id])
        self._log_operation("change_password", "user", target_id=user_id)
        await self._load_users()

    # ---------- 重置二级密码 ----------
    def _reset_out_password(self, user):
        default_pwd = "123456"
        self.confirm_and_run(
            "重置二级密码", f"确定将「{user.get('username','')}」的二级密码重置为 {default_pwd} 吗？",
            self._do_reset_out_password, user['user_id'], default_pwd,
            success_msg=f"二级密码已重置为 {default_pwd}", loading_msg="重置中...")

    async def _do_reset_out_password(self, user_id, new_pwd):
        h1 = hashlib.md5(new_pwd.encode()).hexdigest()
        hashed = hashlib.md5(h1.encode()).hexdigest()
        self.db.execute("UPDATE users SET out_password=? WHERE user_id=?", [hashed, user_id])
        self._log_operation("reset_out_password", "user", target_id=user_id, details="重置为123456")
        admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
        self.db.add_user_message(user_id, '二级密码已重置', f'{admin_name} 将你的二级密码重置为 123456\n请及时修改以保障安全', 'system')
        await self._load_users()

    # ---------- 修改二级密码 ----------
    def _change_out_password(self, user):
        fields = [
            ("新二级密码", "new_pwd", "", "text"),
            ("确认二级密码", "confirm_pwd", "", "text"),
        ]
        def on_submit(data):
            pwd = data['new_pwd'].strip()
            confirm = data['confirm_pwd'].strip()
            if len(pwd) < 6 or len(pwd) > 20:
                self.snack("二级密码长度需6-20位")
                return
            if ' ' in pwd:
                self.snack("二级密码不能包含空格")
                return
            import re
            if not re.match(r'^[a-zA-Z0-9]+$', pwd):
                self.snack("二级密码只能包含英文字母和数字")
                return
            if pwd != confirm:
                self.snack("两次二级密码不一致")
                return
            self.confirm_and_run(
                "修改二级密码", f"确定修改「{user.get('username','')}」的二级密码吗？",
                self._do_change_out_password, user['user_id'], pwd,
                success_msg="二级密码修改成功", loading_msg="修改中...")
        self.form_dialog(f"修改二级密码 - {user.get('username','')}", fields, on_submit)

    async def _do_change_out_password(self, user_id, new_pwd):
        h1 = hashlib.md5(new_pwd.encode()).hexdigest()
        hashed = hashlib.md5(h1.encode()).hexdigest()
        self.db.execute("UPDATE users SET out_password=? WHERE user_id=?", [hashed, user_id])
        self._log_operation("change_out_password", "user", target_id=user_id)
        await self._load_users()

    # ---------- 变更状态（显示状态名） ----------
    def _change_status(self, user):
        status_opts = [f"{k}:{v}" for k, v in STATUS_MAP.items()]
        cur_status = user.get('user_status', 0)
        cur = f"{cur_status}:{_status_name(cur_status)}"
        fields = [("账户状态", "user_status", cur, status_opts)]
        def on_submit(data):
            st = int(str(data['user_status']).split(':')[0])
            st_name = STATUS_MAP.get(st, f'状态{st}')
            self.confirm_and_run(
                "变更状态", f"确定将「{user.get('username','')}」的状态变更为「{st_name}」吗？",
                self._do_change_status, user['user_id'], st,
                success_msg=f"状态已变更为{st_name}", loading_msg="变更中...")
        self.form_dialog(f"变更状态 - {user.get('username','')}", fields, on_submit)

    async def _do_change_status(self, user_id, status):
        # 查询修改前状态
        try:
            old = self.db.fetch_one("SELECT user_status FROM users WHERE user_id=?", [user_id])
            old_status = old['user_status'] if old else None
        except Exception:
            old_status = None
        self.db.execute("UPDATE users SET user_status=? WHERE user_id=?", [status, user_id])
        self._log_operation("change_status", "user", target_id=user_id,
                            details=f"变更为:{_status_name(status)}",
                            before_state={'user_status': old_status, 'status_name': _status_name(old_status) if old_status is not None else None},
                            after_state={'user_status': status, 'status_name': _status_name(status)})
        old_name = _status_name(old_status) if old_status is not None else '未知'
        admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
        self.db.add_user_message(user_id, '账户状态变更',
            f'{admin_name} 将你的账户状态从「{old_name}」变更为「{_status_name(status)}」', 'system')
        await self._load_users()

    # ---------- 删除用户 ----------
    def _delete_user(self, user):
        self.confirm_and_run(
            "删除用户", f"确定删除用户「{user.get('username','')}」(ID:{user['user_id']})吗？此操作不可恢复！",
            self._do_delete_user, user['user_id'],
            success_msg="用户已删除", loading_msg="删除中...")

    async def _do_delete_user(self, user_id):
        # 查询删除前用户信息
        try:
            old_user = self.db.fetch_one("SELECT user_id, username, user_type, user_status FROM users WHERE user_id=?", [user_id])
        except Exception:
            old_user = None
        # foreign key mismatch 是 schema 级错误（user_tasks 引用列无 UNIQUE），
        # 即使用户无关联记录也会报，需临时关闭外键检查
        try:
            self.db.execute("PRAGMA foreign_keys = OFF")
        except Exception:
            pass
        try:
            related_tables = [
                "words_answer_records", "user_chinese_culture_answer_history",
                "user_chinese_culture_questions_history", "user_chinese_culture_answer_summary",
                "chinese_sentences_history", "user_items", "score_record",
                "reward_histories", "item_operation_history", "tasks",
                "user_tasks", "test_config", "practice_control", "User_time_Limits",
                "user_words", "user_mistake_stats",
            ]
            for tbl in related_tables:
                try:
                    self.db.execute(f"DELETE FROM {tbl} WHERE user_id=?", [user_id])
                except Exception:
                    pass
            self.db.execute("DELETE FROM users WHERE user_id=?", [user_id])
            self._log_operation("delete_user", "user", target_id=user_id,
                                target_name=old_user['username'] if old_user else '',
                                details="级联删除相关记录",
                                before_state=dict(old_user) if old_user else None)
        finally:
            try:
                self.db.execute("PRAGMA foreign_keys = ON")
            except Exception:
                pass
        await self._load_users()
