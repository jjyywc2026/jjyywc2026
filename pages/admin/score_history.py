# pages/admin/score_history.py
import flet as ft
from .base import AdminBaseTab

PAGE_SIZE = 20
INITIAL_LIMIT = 20


class ScoreHistoryTab(AdminBaseTab):
    """积分历史记录（分页加载）"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._user_tf = None
        self._current_uid = None
        self._loaded = 0
        self._has_more = True

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

    async def _reload(self, user_id):
        """重新加载（前100条）"""
        import asyncio
        await asyncio.sleep(0.05)
        self._current_uid = user_id
        self._loaded = 0
        self._has_more = True

        def _query():
            try:
                limit = INITIAL_LIMIT
                if user_id:
                    return self.db.fetch_all(
                        """SELECT sr.*, u.username,
                                  st.score_type as type_name,
                                  stn.type_name as sub_type_name
                           FROM (SELECT * FROM score_record WHERE user_id=? ORDER BY score_time DESC LIMIT ?) sr
                           LEFT JOIN users u ON sr.user_id=u.user_id
                           LEFT JOIN score_type st ON sr.score_type=st.type_id
                           LEFT JOIN score_type_name stn ON sr.score_name=stn.id
                           ORDER BY sr.score_time DESC""",
                        [user_id, limit]), None
                else:
                    return self.db.fetch_all(
                        """SELECT sr.*, u.username,
                                  st.score_type as type_name,
                                  stn.type_name as sub_type_name
                           FROM (SELECT * FROM score_record ORDER BY score_time DESC LIMIT ?) sr
                           LEFT JOIN users u ON sr.user_id=u.user_id
                           LEFT JOIN score_type st ON sr.score_type=st.type_id
                           LEFT JOIN score_type_name stn ON sr.score_name=stn.id
                           ORDER BY sr.score_time DESC""",
                        [limit]), None
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
        """加载更多（追加20条）"""
        import asyncio
        if not self._has_more:
            return
        await asyncio.sleep(0.05)
        user_id = self._current_uid
        offset = self._loaded

        def _query():
            try:
                if user_id:
                    return self.db.fetch_all(
                        """SELECT sr.*, u.username,
                                  st.score_type as type_name,
                                  stn.type_name as sub_type_name
                           FROM (SELECT * FROM score_record WHERE user_id=? ORDER BY score_time DESC LIMIT ? OFFSET ?) sr
                           LEFT JOIN users u ON sr.user_id=u.user_id
                           LEFT JOIN score_type st ON sr.score_type=st.type_id
                           LEFT JOIN score_type_name stn ON sr.score_name=stn.id
                           ORDER BY sr.score_time DESC""",
                        [user_id, PAGE_SIZE, offset]), None
                else:
                    return self.db.fetch_all(
                        """SELECT sr.*, u.username,
                                  st.score_type as type_name,
                                  stn.type_name as sub_type_name
                           FROM (SELECT * FROM score_record ORDER BY score_time DESC LIMIT ? OFFSET ?) sr
                           LEFT JOIN users u ON sr.user_id=u.user_id
                           LEFT JOIN score_type st ON sr.score_type=st.type_id
                           LEFT JOIN score_type_name stn ON sr.score_name=stn.id
                           ORDER BY sr.score_time DESC""",
                        [PAGE_SIZE, offset]), None
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

    # 积分类型名称 → 颜色（从score_type表JOIN获取名称）
    _TYPE_COLOR_MAP = {
        "学习积分": ft.Colors.BLUE_600,
        "行为积分": ft.Colors.TEAL_600,
        "兑换积分": ft.Colors.GREEN_600,
        "补偿积分": ft.Colors.ORANGE_600,
        "答题积分": ft.Colors.INDIGO_600,
        "抽奖积分": ft.Colors.RED_600,
        "积分消费": ft.Colors.PURPLE_600,
        "卡券积分": ft.Colors.CYAN_600,
    }

    def _render_rows(self, rows, replace=False):
        tiles = []
        for r in rows or []:
            amount = int(r.get('score_amount') or 0)
            color = ft.Colors.GREEN_600 if amount >= 0 else ft.Colors.RED_600
            sign = "+" if amount >= 0 else ""

            desc = (r.get('description') or '').strip()
            remark = (r.get('remark_edit') or '').strip()

            # 类型名称从score_type表JOIN获取，子类型从score_type_name表JOIN获取
            type_name = (r.get('type_name') or '').strip()
            sub_type = (r.get('sub_type_name') or '').strip()
            if not type_name or type_name == 'v':
                type_name = f"类型{r.get('score_type','?')}"
            type_color = self._TYPE_COLOR_MAP.get(type_name, ft.Colors.GREY_600)
            # 类型标签：主类型 + 子类型（如"积分消费 · 商城购买消费"）
            type_label = f"{type_name} · {sub_type}" if sub_type else type_name

            # 详细原因：description有意义用description，否则用remark_edit
            _meaningless = ('admin', '')
            reason = desc
            if desc in _meaningless or (len(desc) <= 4 and not any(kw in desc for kw in ('测试','挑战','使用','完成','奖励','商城','抽奖','兑换','购买','消费'))):
                reason = remark or desc or "—"
            extra = ""
            if remark and remark != reason and len(remark) > 1:
                extra = f" · {remark}"

            old = r.get('old_score', '')
            new = r.get('new_score', '')
            change = f"{old}→{new}" if old != '' and new != '' else ''
            rid = r.get('id', '')

            tiles.append(self._card_tile(
                # 第一行：用户 + 类型标签 + 积分变化
                ft.Row([
                    ft.CircleAvatar(content=ft.Text(str(r.get('user_id','?')), size=10),
                                    bgcolor=ft.Colors.BLUE_100, color=ft.Colors.BLUE_800, radius=14),
                    ft.Text(f"{r.get('username','?')}", size=13, weight=ft.FontWeight.W_600),
                    ft.Container(
                        content=ft.Text(type_label, size=9, color=ft.Colors.WHITE),
                        bgcolor=type_color, border_radius=4,
                        padding=ft.padding.symmetric(horizontal=5, vertical=1),
                    ),
                    ft.Container(expand=True),
                    ft.Text(f"{sign}{amount} 积分", size=14, weight=ft.FontWeight.BOLD, color=color),
                ], spacing=6, alignment=ft.MainAxisAlignment.START),
                # 第二行：详细原因
                ft.Text(f"{reason}{extra}", size=11, color=ft.Colors.GREY_700),
                # 第三行：余额变化 + 记录ID + 时间
                ft.Row([
                    ft.Text(f"余额: {change}" if change else "", size=10, color=ft.Colors.GREY_500),
                    ft.Text(f"#{rid}", size=9, color=ft.Colors.GREY_400),
                    ft.Container(expand=True),
                    ft.Text(str(r.get('score_time','')), size=10, color=ft.Colors.GREY_400),
                ], spacing=6),
            ))
        if replace:
            self._list_view.controls = tiles
        else:
            # 移除旧的"查看更多"按钮
            self._list_view.controls = [
                c for c in self._list_view.controls
                if not isinstance(c, ft.Container) or not getattr(c, '_is_load_more', False)
            ] + tiles

        # 底部添加"查看更多"或"没有更多了"
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
            self._list_view.controls.append(self._empty("暂无积分记录"))
        self.page.update()
