# pages/admin/tasks.py
import flet as ft
from .base import AdminBaseTab

# 重置规则 → 任务类型显示名
RESET_RULE_NAMES = {"daily": "每日", "weekly": "每周", "monthly": "每月", "none": "不重置"}
CATEGORY_NAMES = {"english": "英语", "guoxue": "国学", "chinese": "语文", "math": "数学"}


class TaskManagementTab(AdminBaseTab):
    """任务管理：增删改查，整行点击编辑"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._users = []
        self._modes = []  # [{mode_id, mode_name, category, description}]
        self._collapsed_users = set()  # 折叠的用户ID集合

    def build(self):
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([
            ft.Row([
                ft.Text("任务列表", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800, expand=True),
                self._action_button("新建任务", ft.Icons.ADD, self._add_task, ft.Colors.GREEN_600),
            ]),
            self._list_view,
        ], spacing=8, expand=True)

    async def load_data(self):
        await self._load_tasks()

    def _safe(self, sql, params=None):
        try:
            return self.db.fetch_all(sql, params) or []
        except Exception as e:
            print(f"[tasks] query fail: {e}")
            return []

    async def _load_tasks(self):
        import asyncio
        await asyncio.sleep(0.05)

        def _query_all():
            # 3条SQL合并为1次批量请求
            statements = [
                ("SELECT user_id, username FROM users ORDER BY username", []),
                ("SELECT mode_id, mode_name, category, description FROM difficulty_modes ORDER BY category, mode_id", []),
                ("SELECT * FROM tasks ORDER BY id", []),
            ]
            try:
                results = self.db.fetch_many(statements)
            except Exception as e:
                print(f"[tasks] batch query fail: {e}")
                return [], [], None, str(e)
            def _safe(idx):
                r = results[idx] if idx < len(results) else []
                return r if r is not None else []
            return _safe(0), _safe(1), _safe(2), None

        self._users, self._modes, rows, err = await asyncio.to_thread(_query_all)
        if err:
            self.snack(f"加载失败: {err}")
            return
        users_map = {u['user_id']: u['username'] for u in self._users}
        modes_map = {m['mode_id']: m for m in self._modes}

        # 按user_id分组
        from collections import defaultdict
        user_groups = defaultdict(list)
        for r in rows or []:
            uid = r.get('user_id') or 0
            user_groups[uid].append(r)
        sorted_uids = sorted(user_groups.keys(), key=lambda x: (0 if x == 0 else 1, x))

        tiles = []
        for uid in sorted_uids:
            user_tasks = user_groups[uid]
            user_name = users_map.get(uid, '全部用户') if uid else '全部用户'
            is_collapsed = uid in self._collapsed_users

            # 分组标题（可点击折叠）
            group_header = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.EXPAND_LESS if not is_collapsed else ft.Icons.EXPAND_MORE,
                            size=16, color=ft.Colors.BLUE_700 if uid else ft.Colors.GREY_600),
                    ft.Container(width=4, height=16, border_radius=2,
                                 bgcolor=ft.Colors.BLUE_500 if uid else ft.Colors.GREY_400),
                    ft.Text(f"{user_name}", size=12, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.BLUE_800 if uid else ft.Colors.GREY_700),
                    ft.Container(
                        content=ft.Text(f"{len(user_tasks)}项", size=9, color=ft.Colors.WHITE,
                                        weight=ft.FontWeight.BOLD),
                        bgcolor=ft.Colors.BLUE_400 if uid else ft.Colors.GREY_400,
                        border_radius=8, padding=ft.padding.symmetric(horizontal=6, vertical=1)),
                    ft.Container(expand=True),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                bgcolor=ft.Colors.BLUE_50 if uid else ft.Colors.GREY_100,
                border_radius=4, margin=ft.margin.only(top=4, bottom=2),
                on_click=lambda e, u=uid: self._toggle_user_group(u),
            )
            tiles.append(group_header)

            if is_collapsed:
                continue

            for r in user_tasks:
                task_status = int(r.get('status') or 0)
                status = "启用" if task_status else "禁用"
                mode = modes_map.get(r.get('mode_id'), {})
                mode_desc = mode.get('description', f"模式{r.get('mode_id',1)}")
                cat_name = CATEGORY_NAMES.get(r.get('content_category', ''), r.get('content_category', ''))
                reset_name = RESET_RULE_NAMES.get(r.get('reset_rule', ''), r.get('reset_rule', ''))
                start = (r.get('start_time') or '')[:10]
                end = (r.get('end_time') or '')[:10]
                tiles.append(self._list_tile(
                    ft.Icon(ft.Icons.TASK_ALT, color=ft.Colors.BLUE_500),
                    ft.Row([
                        ft.Text(f"{r.get('name','')}", size=12, weight=ft.FontWeight.W_600),
                        self._status_chip(bool(task_status), "启用", "禁用"),
                    ], spacing=4),
                    ft.Text(f"{cat_name}·{mode_desc}·{reset_name} · 目标{r.get('target_count',0)} · 奖励{r.get('reward_value',0)}分 · {start}~{end}",
                            size=9, color=ft.Colors.GREY_500, no_wrap=True),
                    trailing=ft.Row([
                        ft.Switch(value=bool(task_status),
                                  on_change=lambda e, tid=r['id']: self._toggle(tid, e.control.value)),
                        ft.IconButton(ft.Icons.DELETE, icon_size=16, icon_color=ft.Colors.RED_400,
                                       on_click=lambda e, t=r: self._delete_task(t)),
                    ], spacing=0),
                    on_click=lambda e, t=r: self._edit_task(t),
                ))
        if not tiles:
            tiles.append(self._empty("暂无任务"))
        self._list_view.controls = tiles
        self.page.update()

    def _toggle_user_group(self, uid):
        """折叠/展开用户分组"""
        if uid in self._collapsed_users:
            self._collapsed_users.discard(uid)
        else:
            self._collapsed_users.add(uid)
        self.page.run_task(self._load_tasks)

    def _toggle(self, task_id, active):
        try:
            t = self.db.fetch_one("SELECT user_id, name FROM tasks WHERE id=?", [task_id])
            self.db.execute("UPDATE tasks SET status=? WHERE id=?", [1 if active else 0, task_id])
            if t and t.get('user_id', 0) != 0:
                admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
                tinfo = self.db.fetch_one("SELECT name, target_count, reward_value, start_time, end_time FROM tasks WHERE id=?", [task_id])
                if tinfo:
                    detail = f"【任务{'启用' if active else '禁用'}】{tinfo.get('name','')}\n操作人：{admin_name}\n目标：{tinfo.get('target_count','?')}次\n奖励：{tinfo.get('reward_value',0)}积分\n时间：{tinfo.get('start_time','') or '不限'} ~ {tinfo.get('end_time','') or '不限'}"
                else:
                    detail = f"【任务{'启用' if active else '禁用'}】{t.get('name','')}\n操作人：{admin_name}"
                self.db.add_user_message(t['user_id'], '任务变更', detail, 'task')
            self.snack("已更新")
        except Exception as e:
            self.snack(f"更新失败: {e}")

    def _add_task(self, e=None):
        self._open_form(None)

    def _edit_task(self, task):
        self._open_form(task)

    def _open_form(self, task):
        is_edit = task is not None
        users = self._users
        modes = self._modes

        def _opt(key_val, label):
            return ft.dropdown.Option(key=str(key_val), text=str(label))

        cat_opts = list(CATEGORY_NAMES.keys())
        reset_opts = list(RESET_RULE_NAMES.keys())

        # 级联下拉（key=ID, text=名称）
        user_dd = ft.Dropdown(label="用户", border_radius=8, expand=True,
            options=[_opt("0", "全部")] + [_opt(u['user_id'], u['username']) for u in users])
        cat_dd = ft.Dropdown(label="内容分类", border_radius=8, expand=True,
            options=[_opt(c, CATEGORY_NAMES.get(c, c)) for c in cat_opts])
        mode_dd = ft.Dropdown(label="模式", border_radius=8, expand=True, options=[])
        reset_dd = ft.Dropdown(label="重置规则", border_radius=8, expand=True,
            options=[_opt(r, RESET_RULE_NAMES.get(r, r)) for r in reset_opts])

        name_tf = ft.TextField(label="任务名称", border_radius=8, expand=True)
        desc_tf = ft.TextField(label="描述", multiline=True, min_lines=2, max_lines=3, border_radius=8, expand=True)
        target_tf = ft.TextField(label="目标次数", keyboard_type=ft.KeyboardType.NUMBER, border_radius=8, expand=True)
        reward_tf = ft.TextField(label="奖励积分", keyboard_type=ft.KeyboardType.NUMBER, border_radius=8, expand=True)
        start_tf = ft.TextField(label="开始日期(YYYY-MM-DD)", border_radius=8, expand=True)
        end_tf = ft.TextField(label="结束日期(YYYY-MM-DD)", border_radius=8, expand=True)

        def refresh_modes(category):
            mlist = [m for m in modes if str(m.get('category')) == str(category)]
            mode_dd.options = [_opt(m['mode_id'], m.get('description', m['mode_name'])) for m in mlist]
            mode_dd.value = mode_dd.options[0].key if mode_dd.options else None

        def on_cat_change(e):
            refresh_modes(cat_dd.value)
            self.page.update()

        cat_dd.on_change = on_cat_change

        # 初始化
        if is_edit:
            name_tf.value = task.get('name', '')
            desc_tf.value = task.get('description', '')
            user_dd.value = str(task.get('user_id', 0))
            cat_dd.value = task.get('content_category', 'english')
            refresh_modes(cat_dd.value)
            mode_dd.value = str(task.get('mode_id', 1))
            reset_dd.value = task.get('reset_rule', 'daily')
            target_tf.value = str(task.get('target_count', 10))
            reward_tf.value = str(task.get('reward_value', 10))
            start_tf.value = (task.get('start_time') or '')[:10]
            end_tf.value = (task.get('end_time') or '')[:10]
        else:
            user_dd.value = "0"
            cat_dd.value = "english"
            refresh_modes("english")
            reset_dd.value = "daily"
            target_tf.value = "10"
            reward_tf.value = "10"

        controls = [name_tf, desc_tf, user_dd, cat_dd, mode_dd, reset_dd,
                    target_tf, reward_tf, start_tf, end_tf]

        def do_submit(e):
            name = name_tf.value.strip()
            if not name:
                self.snack("任务名称不能为空")
                return
            uid = int(user_dd.value or 0)
            mid = int(mode_dd.value or 1)
            params = {
                'name': name, 'description': desc_tf.value or "",
                'user_id': uid, 'content_category': cat_dd.value,
                'mode_id': mid, 'target_count': int(target_tf.value or 1),
                'reward_value': int(reward_tf.value or 0),
                'start_time': start_tf.value or None,
                'end_time': end_tf.value or None,
                'reset_rule': reset_dd.value or 'daily', 'status': 1,
            }
            self._close_dialog(dlg)

            def do_save():
                if is_edit:
                    sets = ", ".join(f"{k}=?" for k in params)
                    self.db.execute(f"UPDATE tasks SET {sets} WHERE id=?", list(params.values()) + [task['id']])
                    before = {k: task.get(k) for k in params}
                    self._log_operation("edit_task", "task", target_id=task['id'],
                                        target_name=name, details=f"模式:{params['mode_id']}",
                                        before_state=before, after_state=params)
                    if params.get('user_id', 0) != 0:
                        admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
                        detail = f"【任务更新】{name}\n操作人：{admin_name}\n目标：{params.get('target_count','?')}次\n奖励：{params.get('reward_value',0)}积分\n时间：{params.get('start_time','') or '不限'} ~ {params.get('end_time','') or '不限'}"
                        self.db.add_user_message(params['user_id'], '任务变更', detail, 'task')
                else:
                    cols = ", ".join(params.keys())
                    ph = ", ".join("?" for _ in params)
                    self.db.execute(f"INSERT INTO tasks ({cols}) VALUES ({ph})", list(params.values()))
                    self._log_operation("add_task", "task", target_name=name,
                                        details=f"模式:{params['mode_id']},用户:{params['user_id']}",
                                        after_state=params)
                    if params.get('user_id', 0) != 0:
                        admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
                        detail = f"【新任务】{name}\n操作人：{admin_name}\n目标：{params.get('target_count','?')}次\n奖励：{params.get('reward_value',0)}积分\n时间：{params.get('start_time','') or '不限'} ~ {params.get('end_time','') or '不限'}\n快去完成吧！"
                        self.db.add_user_message(params['user_id'], '新任务', detail, 'task')

            self.run_save_async(do_save, after_fn=lambda: self.page.run_task(self._load_tasks))

        dlg = ft.AlertDialog(
            title=ft.Text("编辑任务" if is_edit else "新建任务", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column(controls, spacing=8, scroll=ft.ScrollMode.ADAPTIVE),
                                 width=400, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_submit,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)

    def _delete_task(self, task):
        self.confirm_and_run("删除任务", f"确定删除「{task.get('name','')}」吗？",
                             self._do_delete, task['id'],
                             success_msg="已删除", loading_msg="删除中...")

    async def _do_delete(self, task_id):
        t = self.db.fetch_one("SELECT user_id, name FROM tasks WHERE id=?", [task_id])
        self.db.execute("DELETE FROM tasks WHERE id=?", [task_id])
        self._log_operation("delete_task", "task", target_id=task_id)
        if t and t.get('user_id', 0) != 0:
            admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
            self.db.add_user_message(t['user_id'], '任务变更',
                f"【任务删除】{t.get('name','')}\n操作人：{admin_name}\n该任务已被删除", 'task')
        await self._load_tasks()
