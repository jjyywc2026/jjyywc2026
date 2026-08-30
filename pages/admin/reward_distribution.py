# pages/admin/reward_distribution.py
import flet as ft
from .base import AdminBaseTab


class RewardDistributionTab(AdminBaseTab):
    """奖励发放：积分/经验/星星/物品/抽奖次数/礼包"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._user_tf = None
        self._type_dd = None
        self._value_tf = None
        self._item_id_tf = None
        self._qty_tf = None
        self._reason_tf = None
        self._item_row = None

    def build(self):
        self._user_tf = ft.TextField(label="用户ID", hint_text="输入用户ID",
                                     prefix_icon=ft.Icons.PERSON, expand=True,
                                     border_radius=8, height=44,
                                     keyboard_type=ft.KeyboardType.NUMBER)
        self._type_dd = ft.Dropdown(
            label="奖励类型", expand=True, border_radius=8,
            value="experience",
            options=[
                ft.dropdown.Option("experience", "经验"),
                ft.dropdown.Option("item", "物品"),
                ft.dropdown.Option("gift", "礼包"),
            ],
            on_change=self._on_type_change)
        self._value_tf = ft.TextField(label="数量/数值", hint_text="经验值",
                                      prefix_icon=ft.Icons.ADD, expand=True,
                                      border_radius=8, height=44,
                                      keyboard_type=ft.KeyboardType.NUMBER, value="10")
        self._item_id_tf = ft.TextField(label="物品/礼包", hint_text="点击右侧浏览选择",
                                        prefix_icon=ft.Icons.INVENTORY, expand=True,
                                        border_radius=8, height=44, read_only=True)
        self._selected_item_id = None
        self._qty_tf = ft.TextField(label="数量", prefix_icon=ft.Icons.FORMAT_LIST_NUMBERED,
                                    expand=True, border_radius=8, height=44,
                                    keyboard_type=ft.KeyboardType.NUMBER, value="1")
        self._reason_tf = ft.TextField(label="发放原因", hint_text="选填",
                                       prefix_icon=ft.Icons.NOTES, expand=True,
                                       border_radius=8, height=44,
                                       value="管理员手动发放")

        self._item_row = ft.Row([self._item_id_tf, self._qty_tf], spacing=8, visible=False)

        self._browse_btn = self._action_button("浏览物品", ft.Icons.SEARCH, self._browse_items, ft.Colors.TEAL_600)
        self._browse_btn.visible = False  # 默认积分类型，隐藏浏览按钮
        form = ft.Container(
            content=ft.Column([
                ft.Row([self._user_tf, self._type_dd], spacing=8),
                ft.Row([self._value_tf], spacing=8),
                self._item_row,
                ft.Row([self._reason_tf], spacing=8),
                ft.Row([
                    self._browse_btn,
                    ft.Container(expand=True),
                    self._action_button("发放奖励", ft.Icons.SEND, self._on_send, ft.Colors.GREEN_600),
                ], spacing=8),
            ], spacing=10),
            padding=12, bgcolor=ft.Colors.WHITE, border_radius=12,
            shadow=ft.BoxShadow(blur_radius=8, color="#10000000"))

        self._list_view = ft.ListView(spacing=2, expand=True)

        return ft.Column([
            form,
            ft.Container(height=8),
            ft.Text("最近发放记录", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
            self._list_view,
        ], spacing=8, expand=True)

    async def load_data(self):
        await self._load_history()

    def _on_type_change(self, e):
        is_item = self._type_dd.value in ('item', 'gift')
        self._item_row.visible = is_item
        self._value_tf.visible = not is_item
        self._browse_btn.visible = is_item
        self._browse_btn.text = "浏览礼包" if self._type_dd.value == 'gift' else "浏览物品"
        self._value_tf.label = "经验值" if self._type_dd.value == 'experience' else "数量/数值"
        self.page.update()

    def _browse_items(self, e):
        """弹出物品选择列表，按类型筛选，显示详细信息"""
        is_gift = self._type_dd.value == 'gift'
        try:
            if is_gift:
                rows = self.db.fetch_all(
                    "SELECT id, name, category, quality, value, description FROM items WHERE category='礼包' ORDER BY id")
            else:
                rows = self.db.fetch_all(
                    "SELECT id, name, category, quality, value, description FROM items WHERE category != '礼包' ORDER BY category, id")
        except Exception:
            rows = []
        tiles = []
        for idx, r in enumerate(rows or []):
            q = r.get('quality')
            q_color = self.QUALITY_COLORS.get(q, ft.Colors.GREY_700) if q else ft.Colors.GREY_700
            desc = r.get('description') or ''
            if len(desc) > 30:
                desc = desc[:30] + '…'
            if is_gift:
                # 礼包：品质色礼物图标
                leading = ft.Container(
                    width=32, height=32, border_radius=6, bgcolor=q_color,
                    alignment=ft.alignment.center,
                    content=ft.Icon(ft.Icons.CARD_GIFTCARD, color=ft.Colors.WHITE, size=16))
                card_bg = ft.Colors.WHITE if idx % 2 == 0 else ft.Colors.GREY_50
                name_color = q_color
            else:
                # 物品：品质色条
                leading = ft.Container(width=5, height=28, border_radius=3, bgcolor=q_color)
                card_bg = ft.Colors.WHITE if idx % 2 == 0 else ft.Colors.GREY_50
                name_color = q_color
            tiles.append(ft.Container(
                content=ft.Column([
                    ft.Row([
                        leading,
                        ft.Text(f"{r['name']}", size=13, color=name_color, weight=ft.FontWeight.W_700, expand=True),
                        ft.Container(
                            content=ft.Text(f"{q or ''}", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=q_color, border_radius=4,
                            padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                        ft.Text(f"ID:{r['id']}", size=9, color=ft.Colors.GREY_400),
                    ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        ft.Container(
                            content=ft.Text(f"{r.get('category','')}", size=8, color=ft.Colors.WHITE),
                            bgcolor=ft.Colors.GREY_500, border_radius=3,
                            padding=ft.padding.symmetric(horizontal=4, vertical=0)),
                        ft.Text(f"价值:{r.get('value',0)}", size=9, color=ft.Colors.GREY_500),
                        ft.Text(desc, size=9, color=ft.Colors.GREY_400, expand=True, no_wrap=True),
                    ], spacing=5),
                ], spacing=2),
                padding=ft.padding.symmetric(horizontal=10, vertical=7),
                border_radius=8,
                bgcolor=card_bg,
                shadow=ft.BoxShadow(blur_radius=2, color=ft.Colors.GREY_300, offset=ft.Offset(0, 1)),
                on_click=lambda _, rid=r['id'], rname=r['name']: self._select_item(rid, rname, sheet),
            ))
        title = "选择礼包" if is_gift else "选择物品"
        sheet = ft.BottomSheet(
            content=ft.Container(padding=ft.padding.only(top=12, left=16, right=16, bottom=8), content=ft.Column([
                ft.Row([
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18, on_click=lambda e: self.page.close(sheet)),
                    ft.Text(title, size=15, weight=ft.FontWeight.BOLD, expand=True),
                    ft.Text(f"共{len(rows or [])}个", size=10, color=ft.Colors.GREY_500),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(height=1),
                ft.ListView(controls=tiles, height=360, spacing=1),
            ], spacing=4, tight=True)),
            is_scroll_controlled=True, enable_drag=True)
        self.page.open(sheet)

    def _select_item(self, item_id, item_name, sheet):
        self._selected_item_id = item_id
        self._item_id_tf.value = item_name
        self.page.close(sheet)
        self.page.update()

    def _on_send(self, e):
        try:
            uid = int(self._user_tf.value.strip())
        except (ValueError, AttributeError):
            self.snack("请输入有效的用户ID")
            return
        rtype = self._type_dd.value
        reason = self._reason_tf.value or "管理员手动发放"
        type_names = {'experience': '经验', 'item': '物品', 'gift': '礼包'}
        tname = type_names.get(rtype, rtype)

        if rtype in ('item', 'gift'):
            if not self._selected_item_id:
                self.snack("请先浏览选择物品或礼包")
                return
            item_id = self._selected_item_id
            try:
                qty = int(self._qty_tf.value or "1")
            except (ValueError, AttributeError):
                self.snack("请输入有效的数量")
                return
            desc = f"用户{uid}发放{tname} ID:{item_id} ×{qty}"
            self.confirm_and_run("确认发放", f"确定给{desc}吗？",
                                 self._do_send_item, uid, rtype, item_id, qty, reason,
                                 success_msg="发放成功", loading_msg="发放中...")
        else:
            try:
                val = int(self._value_tf.value or "0")
            except ValueError:
                self.snack("请输入有效的数值")
                return
            desc = f"用户{uid}发放{tname} {val}"
            self.confirm_and_run("确认发放", f"确定给{desc}吗？",
                                 self._do_send_value, uid, rtype, val, reason,
                                 success_msg="发放成功", loading_msg="发放中...")

    async def _do_send_item(self, uid, rtype, item_id, qty, reason):
        if rtype == 'gift':
            ok, msg = self.reward_svc.distribute_gift(uid, item_id, qty, reason)
        else:
            ok, msg = self.reward_svc.distribute(uid, 'item', item_id=item_id,
                                                  item_quantity=qty, reason=reason)
        if not ok:
            raise Exception(msg)
        # 奖励发放记录在reward_distribution表（奖励历史），不再写入操作日志
        await self._load_history()

    async def _do_send_value(self, uid, rtype, val, reason):
        ok, msg = self.reward_svc.distribute(uid, rtype, value=val, reason=reason)
        if not ok:
            raise Exception(msg)
        # 奖励发放记录在reward_distribution表（奖励历史），不再写入操作日志
        await self._load_history()

    async def _load_history(self):
        import asyncio
        await asyncio.sleep(0.05)

        def _query():
            try:
                return self.db.fetch_all(
                    """SELECT rd.id, rd.user_id, u.username, rd.reward_type, rd.reward_value,
                              rd.item_id, rd.item_quantity, rd.reason, rd.created_at,
                              i.name as item_name, i.quality as item_quality, i.category as item_category
                       FROM (SELECT * FROM reward_distribution ORDER BY created_at DESC LIMIT 30) rd
                       LEFT JOIN users u ON rd.user_id = u.user_id
                       LEFT JOIN items i ON rd.item_id = i.id
                       ORDER BY rd.created_at DESC"""), None
            except Exception as ex:
                return None, str(ex)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载记录失败: {err}")
            return
        type_names = {'score': '积分', 'experience': '经验', 'star': '星星',
                      'item': '物品', 'lottery': '抽奖', 'gift': '礼包'}
        tiles = []
        for r in rows or []:
            tname = type_names.get(r['reward_type'], r['reward_type'])
            if r['reward_type'] in ('item', 'gift'):
                iname = r.get('item_name') or f"物品#{r['item_id']}"
                iqty = int(r.get('item_quantity') or 0)
                quality = r.get('item_quality')
                q_color = self.QUALITY_COLORS.get(quality, ft.Colors.GREY_700) if quality else ft.Colors.GREY_700
                desc = ft.Row([
                    ft.Container(width=3, height=14, border_radius=2, bgcolor=q_color),
                    ft.Text(f"{tname}: {iname} ×{iqty}", size=12, color=q_color, weight=ft.FontWeight.W_600),
                ], spacing=5)
            else:
                val = int(r.get('reward_value') or 0)
                desc = ft.Text(f"{tname} +{val}", size=12, color=ft.Colors.BLUE_700, weight=ft.FontWeight.W_600)
            tiles.append(self._card_tile(
                # 第一行：用户头像 + 用户名 + 类型标签
                ft.Row([
                    ft.CircleAvatar(content=ft.Text(str(r['user_id']), size=10),
                                    bgcolor=ft.Colors.BLUE_100, color=ft.Colors.BLUE_800, radius=14),
                    ft.Text(f"{r.get('username','?')}", size=13, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Text(tname, size=9, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.BLUE_500, border_radius=4,
                        padding=ft.padding.symmetric(horizontal=5, vertical=1),
                    ),
                ], spacing=8, alignment=ft.MainAxisAlignment.START),
                # 第二行：奖励内容
                desc,
                # 第三行：原因 + 时间
                ft.Row([
                    ft.Text(r.get('reason','') or '—', size=10, color=ft.Colors.GREY_500),
                    ft.Container(expand=True),
                    ft.Text(str(r.get('created_at','')), size=10, color=ft.Colors.GREY_400),
                ], spacing=4),
            ))
        if not tiles:
            tiles.append(self._empty("暂无发放记录"))
        self._list_view.controls = tiles
        self.page.update()
