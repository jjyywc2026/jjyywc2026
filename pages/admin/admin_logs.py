# pages/admin/admin_logs.py
import flet as ft
import json
from .base import AdminBaseTab

# 操作类型中文名映射
OP_TYPE_NAMES = {
    'add_user': '添加用户', 'edit_user': '编辑用户', 'delete_user': '删除用户',
    'reset_password': '重置密码', 'change_password': '修改密码', 'change_status': '变更状态',
    'add_task': '添加任务', 'edit_task': '编辑任务', 'delete_task': '删除任务',
    'add_exchange': '添加商品', 'edit_exchange': '编辑商品', 'delete_exchange': '删除商品',
    'add_item': '添加物品', 'edit_item': '编辑物品', 'delete_item': '删除物品',
    'distribute_reward': '发放奖励',
    'add_mode': '添加模式', 'edit_mode': '编辑模式',
    'add_range': '添加范围', 'edit_range': '编辑范围', 'delete_range': '删除范围',
    'edit_time_limits': '编辑时间限制',
    'add_test_config': '添加测试配置', 'edit_test_config': '编辑测试配置', 'delete_test_config': '删除测试配置',
    'edit_card_window': '编辑赋能卡时间窗口',
    'add_card_date': '添加赋能卡日期', 'edit_card_date': '编辑赋能卡日期', 'delete_card_date': '删除赋能卡日期',
    'add_drop': '添加掉落', 'edit_drop': '编辑掉落', 'delete_drop': '删除掉落',
}

# 目标类型映射
TARGET_TYPE_NAMES = {
    'user': '用户', 'task': '任务', 'exchange_item': '商品', 'item': '物品',
    'reward': '奖励', 'english_mode': '单词模式', 'practice_control': '练习范围',
    'User_time_Limits': '时间限制', 'test_config': '测试配置',
    'card_time_window': '赋能卡时间窗口', 'card_allowed_dates': '赋能卡允许日期',
}

# 操作类型颜色
OP_COLORS = {
    'add': '#16A34A', 'edit': '#2563EB', 'delete': '#DC2626',
    'reset': '#EA580C', 'change': '#7C3AED', 'distribute': '#D97706',
}

_ALL_TYPES = sorted(set(list(OP_TYPE_NAMES.keys())))

# 字段名 → 中文映射
FIELD_NAMES = {
    'username': '用户名', 'password': '密码', 'user_type': '用户类型', 'type': '用户类型',
    'user_status': '账户状态', 'status': '状态', 'total_time': '总时长(分)', 'total_study_time': '总学习时长',
    'studay_time': '今日学习时长', 'study_time': '学习时长', 'evaluation_score': '平均测评分',
    'consecutive_login_days': '连续登录天数', 'sync_enabled': '同步开关',
    'grade_id': '年级', 'volume_id': '册别', 'unit_id': '单元', 'enabled': '启用状态',
    'category': '分类', 'level': '级别', 'question_count': '题目数量',
    'name': '名称', 'description': '描述', 'reward_type': '奖励类型', 'reward_value': '奖励数值',
    'item_id': '物品ID', 'item_name': '物品名称', 'quantity': '数量', 'points_cost': '积分消耗',
    'quality': '品质', 'value': '价值', 'max_stack': '最大堆叠', 'image': '图片',
    'default_input_time': '默认输入时间', 'input_time_max': '输入时间上限',
    'default_daily_limit': '默认每日上限', 'max_daily_limit': '每日最大上限',
    'cool_time': '冷却时间(分)', 'use__computer_start_time': '电脑使用开始',
    'use__computer_end_time': '电脑使用结束',
    'start_time': '开始时间', 'end_time': '结束时间',
    'word_length_min': '单词最小长度', 'word_length_max': '单词最大长度',
    'weight_levels': '权重等级', 'score_per_game': '每局得分', 'time_limit': '时间限制',
    'play_count_per_day': '每日游玩次数', 'words_per_game': '每局单词数',
    'exp_num': '每局经验值', 'min_score': '最低得分', 'max_score': '最高得分',
    'question': '题目', 'option_a': '选项A', 'option_b': '选项B', 'option_c': '选项C',
    'option_d': '选项D', 'answer': '正确答案', 'explanation': '解析',
    'knowledge_point': '知识点', 'difficulty': '难度',
}

# 值映射（字段名 → {原值: 显示值}）
VALUE_MAPPERS = {
    'user_status': {'1': '正常', '2': '冻结', '3': '禁用', 1: '正常', 2: '冻结', 3: '禁用'},
    'status': {'1': '正常', '2': '冻结', '3': '禁用', 1: '正常', 2: '冻结', 3: '禁用'},
    'sync_enabled': {'0': '关闭', '1': '开启', 0: '关闭', 1: '开启'},
    'enabled': {'0': '禁用', '1': '启用', 0: '禁用', 1: '启用', True: '启用', False: '禁用'},
    'user_type': {'admin': '管理员', 'user': '普通用户'},
    'type': {'admin': '管理员', 'user': '普通用户'},
    'quality': {'1': '普通', '2': '优秀', '3': '稀有', '4': '史诗', '5': '传说', '6': '神器',
                1: '普通', 2: '优秀', 3: '稀有', 4: '史诗', 5: '传说', 6: '神器'},
    'difficulty': {'1': '简单', '2': '中等', '3': '困难', 1: '简单', 2: '中等', 3: '困难'},
    'answer': {'1': 'A', '2': 'B', '3': 'C', '4': 'D', 1: 'A', 2: 'B', 3: 'C', 4: 'D'},
}


def _map_field_name(field):
    """字段英文名→中文名"""
    return FIELD_NAMES.get(field, field)


def _map_value(field, value):
    """字段值→可读名称"""
    if value is None:
        return '(空)'
    mapper = VALUE_MAPPERS.get(field)
    if mapper:
        return mapper.get(value, str(value))
    return str(value)


def _parse_state(s):
    """解析before/after状态JSON，返回dict或None"""
    if not s:
        return None
    try:
        d = json.loads(s)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _state_diff(before, after):
    """对比before/after，返回变化字段列表 [(field, old, new), ...]"""
    if not before or not after:
        return []
    changes = []
    keys = set(list(before.keys()) + list(after.keys()))
    for k in sorted(keys):
        old_v = str(before.get(k, ''))
        new_v = str(after.get(k, ''))
        if old_v != new_v:
            changes.append((k, old_v, new_v))
    return changes


class AdminLogsTab(AdminBaseTab):
    """管理员操作日志查看（多维度筛选 + 修改前后对比）"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._keyword_tf = None
        self._type_dd = None
        self._search_ring = None
        self._summary = None
        self._cur_filters = None
        self._loaded = 0
        self._has_more = True
        self._expanded = set()  # 已展开的日志ID
        self._last_rows = []  # 最后加载的日志数据（用于展开/收起时重渲染）

    def build(self):
        tf_style = dict(border_radius=8, height=36, dense=True, text_size=13,
                        content_padding=ft.padding.symmetric(horizontal=10, vertical=0))
        self._keyword_tf = ft.TextField(
            hint_text="搜索管理员/对象/详情/ID", prefix_icon=ft.Icons.SEARCH,
            expand=True, **tf_style,
            on_submit=lambda e: self._do_search())
        self._type_dd = ft.Dropdown(
            hint_text="全部类型", width=130, border_radius=8, value="全部",
            text_size=12, content_padding=ft.padding.symmetric(horizontal=8, vertical=0),
            options=[ft.dropdown.Option("全部")] +
                    [ft.dropdown.Option(t, OP_TYPE_NAMES.get(t, t)) for t in _ALL_TYPES])
        self._search_ring = ft.ProgressRing(width=16, height=16, color=ft.Colors.BLUE_400, visible=False)
        btn = ft.IconButton(
            ft.Icons.SEARCH, icon_size=20, tooltip="搜索",
            on_click=lambda e: self._do_search(),
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 padding=ft.padding.all(8)),
        )
        self._summary = ft.Text("", size=11, color=ft.Colors.GREY_500)
        self._list_view = ft.ListView(spacing=3, expand=True)
        return ft.Column([
            ft.Row([self._keyword_tf, self._type_dd, self._search_ring, btn],
                   spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self._summary,
            self._list_view,
        ], spacing=4, expand=True)

    def _do_search(self):
        keyword = self._keyword_tf.value.strip() if self._keyword_tf.value else None
        otype = self._type_dd.value
        self._expanded.clear()
        self._search_ring.visible = True
        try:
            if self._search_ring.page is not None:
                self._search_ring.update()
        except Exception:
            pass
        self.page.run_task(self._load, keyword, otype)

    async def load_data(self):
        self._expanded.clear()
        await self._load(None, "全部")

    async def _load(self, keyword, op_type):
        import asyncio
        await asyncio.sleep(0.05)
        self._cur_filters = (keyword, op_type)
        self._loaded = 0
        self._has_more = True

        def _query():
            try:
                sql = "SELECT * FROM admin_operation_logs WHERE 1=1"
                params = []
                if op_type and op_type != "全部":
                    sql += " AND operation_type=?"
                    params.append(op_type)
                if keyword:
                    sql += (" AND (details LIKE ? OR target_name LIKE ? OR admin_name LIKE ? "
                            "OR operation_type LIKE ? OR target_type LIKE ? OR CAST(target_id AS TEXT) LIKE ?)")
                    kw = f"%{keyword}%"
                    params.extend([kw, kw, kw, kw, kw, kw])
                sql += " ORDER BY operation_time DESC LIMIT ?"
                params.append(20)
                return self.db.fetch_all(sql, params), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            self._search_ring.visible = False
            return
        self._loaded = len(rows or [])
        self._has_more = self._loaded >= 20
        self._last_rows = list(rows or [])
        self._render_rows(rows, replace=True)
        self._search_ring.visible = False
        try:
            if self._search_ring.page is not None:
                self._search_ring.update()
        except Exception:
            pass

    async def _load_more(self):
        import asyncio
        if not self._has_more or not self._cur_filters:
            return
        await asyncio.sleep(0.05)
        keyword, op_type = self._cur_filters
        offset = self._loaded

        def _query():
            try:
                sql = "SELECT * FROM admin_operation_logs WHERE 1=1"
                params = []
                if op_type and op_type != "全部":
                    sql += " AND operation_type=?"
                    params.append(op_type)
                if keyword:
                    sql += (" AND (details LIKE ? OR target_name LIKE ? OR admin_name LIKE ? "
                            "OR operation_type LIKE ? OR target_type LIKE ? OR CAST(target_id AS TEXT) LIKE ?)")
                    kw = f"%{keyword}%"
                    params.extend([kw, kw, kw, kw, kw, kw])
                sql += " ORDER BY operation_time DESC LIMIT ? OFFSET ?"
                params.extend([20, offset])
                return self.db.fetch_all(sql, params), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            return
        if not rows:
            self._has_more = False
        else:
            self._loaded += len(rows)
            self._last_rows.extend(rows)
            if len(rows) < 20:
                self._has_more = False
        self._render_rows(rows, replace=False)

    def _toggle_expand(self, log_id):
        if log_id in self._expanded:
            self._expanded.remove(log_id)
        else:
            self._expanded.add(log_id)
        # 直接用已加载数据重渲染，不查数据库
        self._render_rows(getattr(self, '_last_rows', []), replace=True)

    def _build_detail(self, r):
        """构建展开详情：修改前后对比"""
        before = _parse_state(r.get('before_state'))
        after = _parse_state(r.get('after_state'))
        changes = _state_diff(before, after)
        parts = []

        # 操作摘要：谁 对 什么 做了什么
        admin = r.get('admin_name', '?')
        tname = OP_TYPE_NAMES.get(r.get('operation_type', ''), r.get('operation_type', ''))
        target = r.get('target_name') or f"ID:{r.get('target_id', '')}"
        summary = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=14, color=ft.Colors.BLUE_500),
                ft.Text(admin, size=11, color=ft.Colors.BLUE_700, weight=ft.FontWeight.W_700),
                ft.Text(tname, size=11, color=ft.Colors.GREY_600),
                ft.Text(f"「{target}」", size=11, color=ft.Colors.GREY_800, weight=ft.FontWeight.W_600),
            ], spacing=4, wrap=True),
            padding=ft.padding.symmetric(vertical=4),
        )
        parts.append(summary)

        # 详情描述
        details = r.get('details', '') or ''
        if details:
            parts.append(ft.Container(
                content=ft.Text(details, size=11, color=ft.Colors.GREY_700),
                padding=ft.padding.symmetric(vertical=2),
            ))

        # 修改前后对比
        if changes:
            diff_rows = []
            for field, old_v, new_v in changes:
                field_cn = _map_field_name(field)
                old_display = _map_value(field, old_v) if old_v else '(空)'
                new_display = _map_value(field, new_v) if new_v else '(空)'
                if len(old_display) > 40:
                    old_display = old_display[:37] + '...'
                if len(new_display) > 40:
                    new_display = new_display[:37] + '...'
                diff_rows.append(ft.Container(
                    content=ft.Column([
                        ft.Text(field_cn, size=10, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_600),
                        ft.Row([
                            ft.Container(
                                content=ft.Text(old_display, size=10, color=ft.Colors.RED_600),
                                bgcolor='#FEF2F2', border_radius=4,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                expand=True,
                            ),
                            ft.Icon(ft.Icons.ARROW_FORWARD, size=12, color=ft.Colors.GREY_400),
                            ft.Container(
                                content=ft.Text(new_display, size=10, color=ft.Colors.GREEN_700),
                                bgcolor='#F0FDF4', border_radius=4,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                expand=True,
                            ),
                        ], spacing=4),
                    ], spacing=2),
                    padding=ft.padding.symmetric(vertical=3),
                ))
            parts.append(ft.Container(
                content=ft.Column([
                    ft.Text(f"变更字段（{len(changes)}项）", size=10, color=ft.Colors.BLUE_600,
                            weight=ft.FontWeight.W_700),
                ] + diff_rows, spacing=2),
                bgcolor='#F8FAFC', border_radius=6, padding=8,
            ))
        elif before or after:
            # 有状态但无差异（或只有一侧）
            state_text = []
            if before:
                state_text.append(ft.Text("修改前:", size=10, color=ft.Colors.GREY_600, weight=ft.FontWeight.W_600))
                for k, v in sorted(before.items()):
                    state_text.append(ft.Text(f"  {_map_field_name(k)}: {_map_value(k, v)}", size=10, color=ft.Colors.GREY_500))
            if after:
                state_text.append(ft.Text("修改后:", size=10, color=ft.Colors.GREY_600, weight=ft.FontWeight.W_600))
                for k, v in sorted(after.items()):
                    state_text.append(ft.Text(f"  {_map_field_name(k)}: {_map_value(k, v)}", size=10, color=ft.Colors.GREY_500))
            parts.append(ft.Container(
                content=ft.Column(state_text, spacing=1),
                bgcolor='#F8FAFC', border_radius=6, padding=8,
            ))

        if not parts:
            parts.append(ft.Text("无详细信息", size=10, color=ft.Colors.GREY_400))

        return ft.Container(
            content=ft.Column(parts, spacing=4, tight=True),
            padding=ft.padding.only(left=36, top=4, bottom=4, right=8),
        )

    def _render_rows(self, rows, replace=False):
        tiles = []
        for r in rows or []:
            log_id = r.get('id', 0)
            otype = r.get('operation_type', '')
            tname = OP_TYPE_NAMES.get(otype, otype)
            ttype = r.get('target_type', '')
            ttname = TARGET_TYPE_NAMES.get(ttype, ttype)
            prefix = otype.split('_')[0] if '_' in otype else otype
            color = OP_COLORS.get(prefix, '#6B7280')
            target = r.get('target_name') or f"ID:{r.get('target_id', '')}"
            details = r.get('details', '') or ''
            op_time = r.get('operation_time', '') or ''
            is_expanded = log_id in self._expanded
            has_state = bool(r.get('before_state') or r.get('after_state'))

            # 第一行：图标 + 管理员 + 类型标签 + 目标标签
            title_row = ft.Row([
                ft.Container(
                    content=ft.Text(tname[:2], size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    width=30, height=30, border_radius=8, bgcolor=color,
                    alignment=ft.alignment.center,
                ),
                ft.Column([
                    ft.Row([
                        ft.Text(f"{r.get('admin_name', '?')}", size=13, weight=ft.FontWeight.W_700,
                                color=ft.Colors.GREY_800),
                        ft.Container(content=ft.Text(tname, size=10, color=ft.Colors.WHITE),
                                     bgcolor=color, border_radius=4,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                        ft.Container(content=ft.Text(ttname, size=10, color=ft.Colors.GREY_700),
                                     bgcolor=ft.Colors.GREY_200, border_radius=4,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                    ], spacing=5),
                    ft.Text(f"{target}", size=11, color=ft.Colors.GREY_600),
                ], spacing=2, expand=True, tight=True),
                ft.Column([
                    ft.Text(op_time[5:16] if len(op_time) >= 16 else op_time, size=10,
                            color=ft.Colors.GREY_400),
                    ft.Row([
                        ft.Icon(ft.Icons.EXPAND_MORE if is_expanded else ft.Icons.CHEVRON_RIGHT,
                                size=14, color=ft.Colors.GREY_400),
                        ft.Text("详情" if has_state else "", size=9, color=ft.Colors.BLUE_400),
                    ], spacing=1) if has_state else ft.Container(),
                ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.END, tight=True),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

            children = [title_row]
            if is_expanded:
                children.append(self._build_detail(r))

            tile = ft.Container(
                content=ft.Column(children, spacing=0, tight=True),
                padding=ft.padding.symmetric(horizontal=10, vertical=8),
                bgcolor=ft.Colors.WHITE,
                border_radius=8,
                margin=ft.margin.only(bottom=2),
                shadow=ft.BoxShadow(blur_radius=4, color="#0A000000", offset=ft.Offset(0, 1)),
                on_click=(lambda e, lid=log_id: self._toggle_expand(lid)) if has_state else None,
                ink=has_state,
            )
            tiles.append(tile)

        if replace:
            self._list_view.controls = tiles
        else:
            self._list_view.controls = [
                c for c in self._list_view.controls
                if not isinstance(c, ft.Container) or not getattr(c, '_is_load_more', False)
            ] + tiles

        if self._has_more:
            btn = ft.Container(
                content=ft.TextButton("查看更多（每次20条）", on_click=lambda e: self.page.run_task(self._load_more)),
                alignment=ft.alignment.center, padding=ft.padding.symmetric(vertical=10),
            )
            btn._is_load_more = True
            self._list_view.controls.append(btn)
        elif self._loaded > 0:
            tip = ft.Container(
                content=ft.Text(f"共加载 {self._loaded} 条，没有更多了", size=11, color=ft.Colors.GREY_400),
                alignment=ft.alignment.center, padding=ft.padding.symmetric(vertical=10),
            )
            tip._is_load_more = True
            self._list_view.controls.append(tip)

        if not self._list_view.controls:
            self._list_view.controls.append(self._empty("暂无符合条件的操作日志"))
        self._summary.value = f"已加载 {self._loaded} 条"
        self.page.update()
