# pages/admin/reward_history.py
import flet as ft
from .base import AdminBaseTab

PAGE_SIZE = 20
INITIAL_LIMIT = 20


class RewardHistoryTab(AdminBaseTab):
    """用户奖励历史记录（分页加载，ID映射为名称）"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._user_tf = None
        self._current_uid = None
        self._loaded = 0
        self._has_more = True
        self._rule_map = {}
        self._gift_map = {}

    def build(self):
        search_row, self._user_tf = self._search_bar("用户ID", "输入用户ID（留空查全部）", self._do_search)
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([search_row, self._list_view], spacing=4, expand=True)

    async def load_data(self):
        await self._reload(None)

    def _do_search(self, keyword):
        uid = None
        if keyword and keyword.strip():
            try:
                uid = int(keyword.strip())
            except ValueError:
                self.snack("请输入有效的用户ID")
                return
        self._search_loading_show(True)
        self.page.run_task(self._reload, uid)

    def _load_rule_map(self):
        try:
            rows = self.db.fetch_all("SELECT rule_id, rule_name FROM reward_rules") or []
            self._rule_map = {r['rule_id']: r.get('rule_name') or f"规则{r['rule_id']}" for r in rows}
        except Exception:
            self._rule_map = {}

    def _load_gift_contents(self):
        """加载礼包内容映射：gift_item_id -> [(item_name, quality, min_qty, max_qty, is_guaranteed)]"""
        self._gift_map = {}
        try:
            rows = self.db.fetch_all("""
                SELECT g.gift_item_id, i.name as item_name, i.quality,
                       g.min_quantity, g.max_quantity, g.is_guaranteed
                FROM gift_pack_rules g
                LEFT JOIN items i ON g.drop_item_id = i.id
                ORDER BY g.gift_item_id, g.is_guaranteed DESC, g.id
            """) or []
            for r in rows:
                gid = r['gift_item_id']
                if gid not in self._gift_map:
                    self._gift_map[gid] = []
                self._gift_map[gid].append(r)
        except Exception:
            pass

    async def _reload(self, user_id):
        import asyncio
        await asyncio.sleep(0.05)
        self._current_uid = user_id
        self._loaded = 0
        self._has_more = True
        self._load_rule_map()
        self._load_gift_contents()

        def _query():
            try:
                # 每张表先按时间倒序取N条，再UNION合并，避免全表扫描
                per_limit = limit = INITIAL_LIMIT
                where_user = "WHERE user_id=?" if user_id else ""
                union_sql = f"""
                    SELECT * FROM (
                        SELECT user_id, reward_type, reward_value, item_id, item_quantity,
                               rule_id, milestone_number, awarded_at,
                               CAST(NULL AS TEXT) as reason, CAST(NULL AS TEXT) as operator
                        FROM reward_histories {where_user}
                        ORDER BY awarded_at DESC LIMIT {per_limit}
                    ) h
                    UNION ALL
                    SELECT * FROM (
                        SELECT user_id, reward_type, reward_value, item_id, item_quantity,
                               CAST(NULL AS INTEGER) as rule_id, CAST(NULL AS INTEGER) as milestone_number,
                               created_at as awarded_at, reason, operator
                        FROM reward_distribution {where_user}
                        ORDER BY created_at DESC LIMIT {per_limit}
                    ) d
                    UNION ALL
                    SELECT * FROM (
                        SELECT user_id, 'item' as reward_type, CAST(NULL AS REAL) as reward_value,
                               item_id, quantity as item_quantity,
                               CAST(NULL AS INTEGER) as rule_id, CAST(NULL AS INTEGER) as milestone_number,
                               operation_time as awarded_at, details as reason, '管理员' as operator
                        FROM item_operation_history
                        WHERE operation_type='admin_grant' {('AND user_id=?' if user_id else '')}
                        ORDER BY operation_time DESC LIMIT {per_limit}
                    ) g
                """
                params = [user_id, user_id, user_id, limit] if user_id else [limit]
                return self.db.fetch_all(
                    f"""SELECT combined.*, u.username, i.name as item_name, i.quality as item_quality
                        FROM ({union_sql}) combined
                        LEFT JOIN users u ON combined.user_id=u.user_id
                        LEFT JOIN items i ON combined.item_id=i.id
                        ORDER BY combined.awarded_at DESC LIMIT ?""",
                    params), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            self._search_loading_show(False)
            return
        self._loaded = len(rows or [])
        self._has_more = self._loaded >= INITIAL_LIMIT
        self._render_rows(rows, replace=True)
        self._search_loading_show(False)

    async def _load_more(self):
        import asyncio
        if not self._has_more:
            return
        await asyncio.sleep(0.05)
        user_id = self._current_uid
        offset = self._loaded

        def _query():
            try:
                # 每张表先取(offset+limit)条，再UNION合并排序，避免全表扫描
                per_limit = offset + PAGE_SIZE
                where_user = "WHERE user_id=?" if user_id else ""
                union_sql = f"""
                    SELECT * FROM (
                        SELECT user_id, reward_type, reward_value, item_id, item_quantity,
                               rule_id, milestone_number, awarded_at,
                               CAST(NULL AS TEXT) as reason, CAST(NULL AS TEXT) as operator
                        FROM reward_histories {where_user}
                        ORDER BY awarded_at DESC LIMIT {per_limit}
                    ) h
                    UNION ALL
                    SELECT * FROM (
                        SELECT user_id, reward_type, reward_value, item_id, item_quantity,
                               CAST(NULL AS INTEGER) as rule_id, CAST(NULL AS INTEGER) as milestone_number,
                               created_at as awarded_at, reason, operator
                        FROM reward_distribution {where_user}
                        ORDER BY created_at DESC LIMIT {per_limit}
                    ) d
                    UNION ALL
                    SELECT * FROM (
                        SELECT user_id, 'item' as reward_type, CAST(NULL AS REAL) as reward_value,
                               item_id, quantity as item_quantity,
                               CAST(NULL AS INTEGER) as rule_id, CAST(NULL AS INTEGER) as milestone_number,
                               operation_time as awarded_at, details as reason, '管理员' as operator
                        FROM item_operation_history
                        WHERE operation_type='admin_grant' {('AND user_id=?' if user_id else '')}
                        ORDER BY operation_time DESC LIMIT {per_limit}
                    ) g
                """
                params = [user_id, user_id, user_id, PAGE_SIZE, offset] if user_id else [PAGE_SIZE, offset]
                return self.db.fetch_all(
                    f"""SELECT combined.*, u.username, i.name as item_name, i.quality as item_quality
                        FROM ({union_sql}) combined
                        LEFT JOIN users u ON combined.user_id=u.user_id
                        LEFT JOIN items i ON combined.item_id=i.id
                        ORDER BY combined.awarded_at DESC LIMIT ? OFFSET ?""",
                    params), None
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
            if len(rows) < PAGE_SIZE:
                self._has_more = False
        self._render_rows(rows, replace=False)

    def _render_rows(self, rows, replace=False):
        type_names = {'score': '积分', 'experience': '经验', 'star': '星星',
                      'item': '物品', 'lottery': '抽奖', 'gift': '礼包'}
        type_colors = {'score': '#4CAF50', 'experience': '#2196F3',
                       'star': '#FF9800', 'item': '#9C27B0', 'lottery': '#FF5722', 'gift': '#E91E63'}
        tiles = []
        for r in rows or []:
            rt = type_names.get(r['reward_type'], r['reward_type'] or '未知')
            rcolor = type_colors.get(r['reward_type'], '#9E9E9E')

            # 奖励名称（rule_name 或 管理员原因）
            if r.get('operator'):
                reward_name = r.get('reason') or '管理员发放'
            else:
                reward_name = self._rule_map.get(r.get('rule_id'), f"规则{r.get('rule_id','')}")
                ms = r.get('milestone_number')
                if ms:
                    reward_name = f"{reward_name} · 里程碑{ms}"

            # 奖励内容
            item_name = r.get('item_name') or f"物品{r.get('item_id','')}"
            quality = r.get('item_quality')
            name_color = self.QUALITY_COLORS.get(quality, '#9E9E9E') if quality else '#424242'
            qty = r.get('item_quantity')
            is_gift = (r['reward_type'] == 'gift')

            if is_gift:
                # 管理员发放礼包：显示礼包内容
                gift_items = self._gift_map.get(r.get('item_id'), [])
                if gift_items:
                    parts = []
                    for gi in gift_items:
                        gname = gi.get('item_name') or '?'
                        mn, mx = gi.get('min_quantity', 1), gi.get('max_quantity', 1)
                        qty_str = f"{mn}-{mx}" if mn != mx else str(mn)
                        is_g = gi.get('is_guaranteed')
                        guaranteed = "必掉" if (is_g == 1 or is_g == '1' or is_g is True) else "概率"
                        parts.append(f"{gname}×{qty_str}({guaranteed})")
                    content_text = "含: " + "、".join(parts)
                    content_row = ft.Text(content_text, size=11, color='#5D4037', no_wrap=False)
                else:
                    content_row = ft.Text(f"{item_name} ×{qty}", size=12, color=name_color, weight=ft.FontWeight.W_600)
            elif r['reward_type'] == 'item':
                content_row = ft.Row([
                    ft.Text(item_name, size=13, color=name_color, weight=ft.FontWeight.W_700),
                    ft.Text(f" ×{qty}", size=12, color=ft.Colors.GREY_700, weight=ft.FontWeight.W_600),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            else:
                content_row = ft.Text(f"{rt} +{r.get('reward_value',0)}", size=13, color=rcolor, weight=ft.FontWeight.W_700)

            q_chip = self._quality_chip(quality) if quality and not is_gift else ft.Container()

            # 时间
            t = str(r.get('awarded_at', ''))[:19]

            # 三行卡片
            card = ft.Container(
                content=ft.Column([
                    # 第一行：用户名 + 类型
                    ft.Row([
                        ft.Text(r.get('username','?'), size=11, color=ft.Colors.GREY_600),
                        ft.Container(
                            content=ft.Text(rt, size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=rcolor, border_radius=3,
                            padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                        q_chip,
                    ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    # 第二行：奖励名称（大字）
                    ft.Text(reward_name, size=14, weight=ft.FontWeight.W_700, color='#1A237E', no_wrap=True),
                    # 第三行：奖励内容
                    content_row,
                    # 第四行：时间
                    ft.Text(t, size=10, color=ft.Colors.GREY_400),
                ], spacing=3, tight=True),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                bgcolor=ft.Colors.WHITE, border_radius=8,
                margin=ft.margin.only(bottom=4),
            )
            tiles.append(card)

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
                alignment=ft.alignment.center, padding=ft.padding.symmetric(vertical=8),
            )
            btn._is_load_more = True
            self._list_view.controls.append(btn)
        elif self._loaded > INITIAL_LIMIT or (not self._has_more and self._loaded > 0):
            tip = ft.Container(
                content=ft.Text(f"共加载 {self._loaded} 条，没有更多了", size=10, color=ft.Colors.GREY_400),
                alignment=ft.alignment.center, padding=ft.padding.symmetric(vertical=8),
            )
            tip._is_load_more = True
            self._list_view.controls.append(tip)

        if not self._list_view.controls:
            self._list_view.controls.append(self._empty("暂无奖励记录"))
        self.page.update()
