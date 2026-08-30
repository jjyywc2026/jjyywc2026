# pages/admin/gift_config.py
import flet as ft
from .base import AdminBaseTab


class GiftConfigTab(AdminBaseTab):
    """礼包配置：礼包列表 → 点击进入掉落配置"""

    def __init__(self, page):
        super().__init__(page)
        self._content_col = None
        self._view = 'list'  # 'list' | 'drops'
        self._current_gift_id = None
        self._current_gift_name = ""
        self._list_view = None
        self._search_tf = None
        self._search_keyword = ""

    def build(self):
        self._content_col = ft.Column(spacing=8, expand=True, scroll=ft.ScrollMode.ADAPTIVE)
        return self._content_col

    async def load_data(self):
        self._view = 'list'
        await self._show_gift_list()

    # ---------- 礼包列表视图 ----------
    async def _show_gift_list(self):
        import asyncio
        await asyncio.sleep(0.05)

        def _query():
            try:
                sql = """SELECT i.id, i.name, i.category, i.quality, i.value, i.description,
                              (SELECT COUNT(*) FROM gift_pack_rules g WHERE g.gift_item_id=i.id) as cfg_count,
                              (SELECT COALESCE(SUM(drop_probability),0) FROM gift_pack_rules g WHERE g.gift_item_id=i.id) as total_prob,
                              (SELECT GROUP_CONCAT(ii.name, '、') FROM gift_pack_rules g
                               LEFT JOIN items ii ON g.drop_item_id=ii.id
                               WHERE g.gift_item_id=i.id ORDER BY g.drop_probability DESC LIMIT 5) as drop_names
                       FROM items i
                       WHERE i.category='礼包'"""
                params = []
                if self._search_keyword:
                    sql += " AND i.name LIKE ?"
                    params.append(f"%{self._search_keyword}%")
                sql += " ORDER BY i.id"
                return self.db.fetch_all(sql, params), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载礼包失败: {err}")
            rows = []

        tiles = []
        for idx, r in enumerate(rows or []):
            cfg_count = int(r.get('cfg_count', 0) or 0)
            total_prob = float(r.get('total_prob') or 0)
            quality = r.get('quality', '普通')
            q_color = self.QUALITY_COLORS.get(quality, "#9E9E9E")
            drop_names = r.get('drop_names') or ''
            if drop_names and cfg_count > 5:
                drop_names = drop_names + f' 等{cfg_count}种'
            desc = (r.get('description') or '')[:35]
            card_bg = ft.Colors.WHITE if idx % 2 == 0 else ft.Colors.GREY_50
            tiles.append(ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(width=5, height=36, border_radius=3, bgcolor=q_color),
                        ft.Container(
                            width=36, height=36, border_radius=8, bgcolor=q_color,
                            alignment=ft.alignment.center,
                            content=ft.Icon(ft.Icons.CARD_GIFTCARD, color=ft.Colors.WHITE, size=18),
                        ),
                        ft.Column([
                            ft.Row([
                                ft.Text(f"{r['name']}", size=13, weight=ft.FontWeight.BOLD, color=q_color),
                                self._quality_chip(quality),
                            ], spacing=4),
                            ft.Text(f"ID:{r['id']} · 价值:{r.get('value',0)} · {cfg_count}种掉落 · 总概率:{total_prob:.1f}",
                                    size=9, color=ft.Colors.GREY_500),
                        ], spacing=1, expand=True),
                        ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14, color=ft.Colors.GREY_400),
                    ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Text(drop_names, size=9, color=ft.Colors.GREY_600, no_wrap=True) if drop_names else ft.Container(),
                    ft.Text(desc, size=8, color=ft.Colors.GREY_400, no_wrap=True) if desc else ft.Container(),
                ], spacing=2),
                padding=ft.padding.symmetric(horizontal=10, vertical=8),
                border_radius=8,
                bgcolor=card_bg,
                shadow=ft.BoxShadow(blur_radius=2, color=ft.Colors.GREY_300, offset=ft.Offset(0, 1)),
                on_click=lambda e, gift=r: self._open_drops(gift),
            ))
        if not tiles:
            tiles.append(self._empty("暂无礼包，请先在物品管理中添加分类为'礼包'的物品"))

        self._search_tf = ft.TextField(
            hint_text="搜索礼包名称", prefix_icon=ft.Icons.SEARCH,
            expand=True, border_radius=8, height=36, dense=True, text_size=12,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=0),
            value=self._search_keyword,
            on_submit=lambda e: self._do_search(),
        )
        search_btn = ft.IconButton(
            ft.Icons.SEARCH, icon_size=18, tooltip="搜索",
            on_click=lambda e: self._do_search(),
            style=ft.ButtonStyle(bgcolor=ft.Colors.PURPLE_600, color=ft.Colors.WHITE,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 padding=ft.padding.all(8)),
        )
        self._content_col.controls = [
            ft.Row([
                ft.Text("礼包列表", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE_800),
                ft.Container(expand=True),
                ft.Text(f"共{len(rows or [])}个", size=11, color=ft.Colors.GREY_500),
            ]),
            ft.Row([self._search_tf, search_btn], spacing=6,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.ListView(controls=tiles, spacing=2, expand=True),
        ]
        self.page.update()

    def _do_search(self):
        self._search_keyword = (self._search_tf.value or "").strip()
        self.page.run_task(self._show_gift_list)

    def _open_drops(self, gift):
        self._current_gift_id = gift['id']
        self._current_gift_name = gift['name']
        self._view = 'drops'
        self.page.run_task(self._show_drops_view)

    # ---------- 掉落配置视图 ----------
    async def _show_drops_view(self):
        import asyncio
        await asyncio.sleep(0.05)
        self._list_view = ft.ListView(spacing=2, expand=True)
        self._content_col.controls = [
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, icon_size=20, on_click=self._back_to_list),
                ft.Text(f"{self._current_gift_name} 掉落配置", size=14, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.PURPLE_800),
                ft.Container(expand=True),
                self._action_button("添加", ft.Icons.ADD, self._add_drop, ft.Colors.GREEN_600),
            ], spacing=4),
            self._list_view,
        ]
        self.page.update()
        await self._load_drops()

    def _back_to_list(self, e=None):
        self._view = 'list'
        self.page.run_task(self._show_gift_list)

    async def _load_drops(self):
        import asyncio
        await asyncio.sleep(0.05)
        if not self._current_gift_id:
            return
        try:
            rows = self.db.fetch_all(
                """SELECT gpr.*, i.name as item_name, i.quality as item_quality
                   FROM gift_pack_rules gpr
                   LEFT JOIN items i ON gpr.drop_item_id = i.id
                   WHERE gpr.gift_item_id=? ORDER BY gpr.drop_probability DESC""",
                [self._current_gift_id])
        except Exception as e:
            self.snack(f"加载失败: {e}")
            return
        tiles = []
        total_prob = sum(float(r.get('drop_probability') or 0) for r in rows or [])
        for idx, r in enumerate(rows or []):
            prob = float(r.get('drop_probability') or 0)
            pct = (prob / total_prob * 100) if total_prob > 0 else 0
            is_g = r.get('is_guaranteed')
            guaranteed = "保底" if (is_g == 1 or is_g == '1' or is_g is True) else ""
            item_q = r.get('item_quality')
            q_color = self.QUALITY_COLORS.get(item_q, ft.Colors.GREY_700) if item_q else ft.Colors.GREY_700
            min_q = r.get('min_quantity', 1) or 1
            max_q = r.get('max_quantity', 1) or 1
            qty_range = f"{min_q}~{max_q}" if min_q != max_q else str(r.get('drop_quantity',1))
            card_bg = ft.Colors.WHITE if idx % 2 == 0 else ft.Colors.GREY_50
            tiles.append(ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(width=5, height=28, border_radius=2, bgcolor=q_color),
                        ft.Text(f"{r.get('item_name', '物品' + str(r['drop_item_id']))}", size=12,
                                weight=ft.FontWeight.W_700, color=q_color, expand=True),
                        self._quality_chip(item_q) if item_q else ft.Container(),
                        ft.Container(
                            content=ft.Text(guaranteed, size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=ft.Colors.ORANGE_600, border_radius=4,
                            padding=ft.padding.symmetric(horizontal=4, vertical=1),
                        ) if guaranteed else ft.Container(),
                        ft.IconButton(ft.Icons.DELETE, icon_size=14, icon_color=ft.Colors.RED_400,
                                       on_click=lambda e, item=r: self._delete_drop(item)),
                    ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        ft.Text(f"数量:{qty_range}", size=9, color=ft.Colors.GREY_600),
                        ft.Text(f"概率:{prob} ({pct:.1f}%)", size=9, color=ft.Colors.GREY_600),
                        ft.Text(f"权重:{r.get('weight','-')}", size=9, color=ft.Colors.GREY_600),
                        ft.Text(f"ID:{r['drop_item_id']}", size=8, color=ft.Colors.GREY_400),
                        ft.Container(expand=True),
                    ], spacing=6),
                ], spacing=2),
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=6,
                bgcolor=card_bg,
                shadow=ft.BoxShadow(blur_radius=2, color=ft.Colors.GREY_300, offset=ft.Offset(0, 1)),
                on_click=lambda e, item=r: self._edit_drop(item),
            ))
        if not tiles:
            tiles.append(self._empty("暂无掉落配置，点击右上角添加"))
        self._list_view.controls = tiles
        self.page.update()

    # ---------- 增删改 ----------
    def _add_drop(self, e=None):
        self._open_form(None)

    def _edit_drop(self, item):
        self._open_form(item)

    def _open_form(self, item):
        is_edit = item is not None
        # 选中的掉落物品ID和名称
        sel_drop_id = item.get('drop_item_id') if is_edit else None
        sel_drop_name = item.get('item_name') if is_edit else None

        # 物品选择显示
        item_btn = ft.ElevatedButton(
            text=f"已选: {sel_drop_name}" if sel_drop_name else "点击选择掉落物品",
            icon=ft.Icons.SEARCH,
            expand=True,
            style=ft.ButtonStyle(bgcolor=ft.Colors.PURPLE_50, color=ft.Colors.PURPLE_800),
            on_click=lambda e: self._browse_drop_items(dlg, item_btn))

        qty_tf = ft.TextField(label="掉落数量", value=str(item.get('drop_quantity',1) if is_edit else 1),
                              keyboard_type=ft.KeyboardType.NUMBER, border_radius=8)
        prob_tf = ft.TextField(label="掉落概率", value=str(item.get('drop_probability',1.0) if is_edit else 1.0),
                               border_radius=8)
        weight_tf = ft.TextField(label="权重", value=str(item.get('weight',1) if is_edit else 1),
                                 keyboard_type=ft.KeyboardType.NUMBER, border_radius=8)
        guar_dd = ft.Dropdown(label="是否保底", border_radius=8,
            options=[ft.dropdown.Option("否"), ft.dropdown.Option("是")],
            value="是" if (is_edit and item.get('is_guaranteed')) else "否")
        min_tf = ft.TextField(label="最小数量", value=str(item.get('min_quantity',1) if is_edit else 1),
                              keyboard_type=ft.KeyboardType.NUMBER, border_radius=8)
        max_tf = ft.TextField(label="最大数量", value=str(item.get('max_quantity',1) if is_edit else 1),
                              keyboard_type=ft.KeyboardType.NUMBER, border_radius=8)

        def do_submit(e):
            drop_id = dlg._sel_drop_id
            if drop_id is None:
                self.snack("请先选择掉落物品")
                return
            try:
                drop_id = int(drop_id)
                qty = int(qty_tf.value or 1)
                prob = float(prob_tf.value or 1.0)
                weight = int(weight_tf.value or 1)
                guaranteed = 1 if guar_dd.value == "是" else 0
                min_q = int(min_tf.value or 1)
                max_q = int(max_tf.value or 1)
                if is_edit:
                    self.db.execute(
                        """UPDATE gift_pack_rules SET drop_item_id=?, drop_quantity=?, drop_probability=?,
                           is_guaranteed=?, min_quantity=?, max_quantity=?, weight=? WHERE id=?""",
                        [drop_id, qty, prob, guaranteed, min_q, max_q, weight, item['id']])
                else:
                    self.db.execute(
                        """INSERT INTO gift_pack_rules
                           (gift_item_id, drop_item_id, drop_quantity, drop_probability, is_guaranteed, min_quantity, max_quantity, weight)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        [self._current_gift_id, drop_id, qty, prob, guaranteed, min_q, max_q, weight])
                op = 'edit_drop' if is_edit else 'add_drop'
                self._log_operation(op, 'gift_pack_rule', target_id=item['id'] if is_edit else self._current_gift_id,
                                    target_name=f"礼包#{self._current_gift_id} 掉落物品#{drop_id}",
                                    details=f"数量:{qty} 概率:{prob} 保底:{'是' if guaranteed else '否'} 最小:{min_q} 最大:{max_q} 权重:{weight}")
                self.snack("已保存")
                self._close_dialog(dlg)
                self.page.run_task(self._load_drops)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        dlg = ft.AlertDialog(
            title=ft.Text("编辑掉落" if is_edit else "添加掉落", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column([
                item_btn,
                qty_tf, prob_tf, weight_tf, guar_dd, min_tf, max_tf,
            ], spacing=8, scroll=ft.ScrollMode.ADAPTIVE), width=380, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_submit,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.PURPLE_600, color=ft.Colors.WHITE)),
            ],
        )
        # 保存选中状态到dialog属性，供_browse_drop_items回调使用
        dlg._sel_drop_id = sel_drop_id
        dlg._sel_drop_name = sel_drop_name
        self.page.open(dlg)

    def _browse_drop_items(self, dlg, item_btn):
        """浏览选择掉落物品（排除礼包本身）"""
        try:
            rows = self.db.fetch_all(
                "SELECT id, name, category, quality, value, description FROM items WHERE category != '礼包' ORDER BY category, id")
        except Exception:
            rows = []
        tiles = []
        for idx, r in enumerate(rows or []):
            q = r.get('quality')
            q_color = self.QUALITY_COLORS.get(q, ft.Colors.GREY_700) if q else ft.Colors.GREY_700
            desc = (r.get('description') or '')[:25]
            card_bg = ft.Colors.WHITE if idx % 2 == 0 else ft.Colors.GREY_50
            tiles.append(ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(width=5, height=22, border_radius=3, bgcolor=q_color),
                        ft.Text(f"{r['name']}", size=12, color=q_color, weight=ft.FontWeight.W_700, expand=True),
                        ft.Container(
                            content=ft.Text(f"{q or ''}", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=q_color, border_radius=3,
                            padding=ft.padding.symmetric(horizontal=4, vertical=0)),
                        ft.Text(f"ID:{r['id']}", size=8, color=ft.Colors.GREY_400),
                    ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        ft.Container(content=ft.Text(f"{r.get('category','')}", size=8, color=ft.Colors.WHITE),
                                     bgcolor=ft.Colors.GREY_500, border_radius=3,
                                     padding=ft.padding.symmetric(horizontal=3, vertical=0)),
                        ft.Text(f"价值:{r.get('value',0)}", size=8, color=ft.Colors.GREY_500),
                        ft.Text(desc, size=8, color=ft.Colors.GREY_400, expand=True, no_wrap=True),
                    ], spacing=4),
                ], spacing=1),
                padding=ft.padding.symmetric(horizontal=8, vertical=5),
                border_radius=6,
                bgcolor=card_bg,
                shadow=ft.BoxShadow(blur_radius=2, color=ft.Colors.GREY_300, offset=ft.Offset(0, 1)),
                on_click=lambda _, rid=r['id'], rname=r['name']: self._select_drop_item(dlg, item_btn, rid, rname, sheet),
            ))
        sheet = ft.BottomSheet(
            content=ft.Container(padding=ft.padding.only(top=12, left=16, right=16, bottom=8), content=ft.Column([
                ft.Row([
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18, on_click=lambda e: self.page.close(sheet)),
                    ft.Text("选择掉落物品", size=15, weight=ft.FontWeight.BOLD, expand=True),
                    ft.Text(f"共{len(rows or [])}个", size=10, color=ft.Colors.GREY_500),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(height=1),
                ft.ListView(controls=tiles, height=360, spacing=1),
            ], spacing=4, tight=True)),
            is_scroll_controlled=True, enable_drag=True)
        self.page.open(sheet)

    def _select_drop_item(self, dlg, item_btn, item_id, item_name, sheet):
        dlg._sel_drop_id = item_id
        dlg._sel_drop_name = item_name
        item_btn.text = f"已选: {item_name}"
        self.page.close(sheet)
        self.page.update()

    def _delete_drop(self, item):
        self.confirm_and_run("删除掉落", "确定删除该掉落配置吗？",
                             self._do_delete, item['id'],
                             success_msg="已删除", loading_msg="删除中...")

    async def _do_delete(self, drop_id):
        self.db.execute("DELETE FROM gift_pack_rules WHERE id=?", [drop_id])
        self._log_operation('delete_drop', 'gift_pack_rule', target_id=drop_id,
                            target_name=f"礼包#{self._current_gift_id} 掉落#{drop_id}",
                            details="删除掉落配置")
        await self._load_drops()
