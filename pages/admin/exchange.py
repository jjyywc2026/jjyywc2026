# pages/admin/exchange.py
import flet as ft
from .base import AdminBaseTab

CATEGORY_NAMES = {1: '时长', 2: '物品', 3: '礼包'}
STATUS_NAMES = {1: '上架', 0: '下架'}


def _status_name(val):
    """状态值转名称，None/未知统一视为下架"""
    if val is None:
        return '下架'
    try:
        return STATUS_NAMES.get(int(val), '下架')
    except (ValueError, TypeError):
        return '下架'


class ExchangeManagementTab(AdminBaseTab):
    """商品管理：分类/状态显示名字，时长类显隐时长字段"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None

    def build(self):
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([
            ft.Row([
                ft.Text("商品管理", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800, expand=True),
                self._action_button("添加商品", ft.Icons.ADD, self._add_item, ft.Colors.GREEN_600),
            ]),
            self._list_view,
        ], spacing=8, expand=True)

    async def load_data(self):
        await self._load_items()

    async def _load_items(self):
        import asyncio
        await asyncio.sleep(0.05)

        def _query():
            try:
                return self.db.fetch_all("SELECT * FROM exchange_items ORDER BY category, id"), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            return
        tiles = []
        for r in rows or []:
            cat = CATEGORY_NAMES.get(r.get('category'), f"分类{r.get('category')}")
            status = _status_name(r.get('status'))
            is_on = str(r.get('status')) == '1'
            time_info = f" · {r.get('time_score',0)}分钟" if r.get('category') == 1 else ""
            tiles.append(self._list_tile(
                ft.Icon(ft.Icons.SHOPPING_BAG, color=ft.Colors.PURPLE_500),
                ft.Row([
                    ft.Text(f"{r.get('name','')}", size=12, weight=ft.FontWeight.W_600),
                    self._onoff_chip(r.get('status'), "上架", "下架"),
                ], spacing=4),
                ft.Text(f"{cat}{time_info} · {r.get('points_required',0)}积分 · 库存:{r.get('stock_quantity','∞')}",
                        size=9, color=ft.Colors.GREY_500, no_wrap=True),
                trailing=ft.Row([
                    ft.IconButton(ft.Icons.DELETE, icon_size=16, icon_color=ft.Colors.RED_400,
                                   on_click=lambda e, item=r: self._delete_item(item)),
                ], spacing=0),
                on_click=lambda e, item=r: self._edit_item(item),
            ))
        if not tiles:
            tiles.append(self._empty("暂无商品"))
        self._list_view.controls = tiles
        self.page.update()

    def _add_item(self, e=None):
        self._open_form(None)

    def _edit_item(self, item):
        self._open_form(item)

    def _open_form(self, item):
        is_edit = item is not None

        def _opt(key_val, label):
            return ft.dropdown.Option(key=str(key_val), text=str(label))

        # 时长字段（仅分类=时长时显示）
        time_field = ft.TextField(
            label="时长(分钟)", value=str(item.get('time_score', 0) if is_edit else 0),
            keyboard_type=ft.KeyboardType.NUMBER, border_radius=8, expand=True,
            visible=(item.get('category') == 1 if is_edit else True))

        cat_dd = ft.Dropdown(
            label="分类", value=str(item.get('category', 1) if is_edit else 1),
            options=[_opt(k, v) for k, v in CATEGORY_NAMES.items()],
            border_radius=8, expand=True)

        def on_cat_change(e):
            cat_id = int(cat_dd.value or 1)
            time_field.visible = (cat_id == 1)
            self.page.update()

        cat_dd.on_change = on_cat_change

        name_tf = ft.TextField(label="商品名称", value=item.get('name') if is_edit else "",
                               border_radius=8, expand=True)
        desc_tf = ft.TextField(label="描述", value=item.get('description') if is_edit else "",
                               multiline=True, min_lines=2, max_lines=3, border_radius=8, expand=True)
        points_tf = ft.TextField(label="所需积分", value=str(item.get('points_required', 100) if is_edit else 100),
                                 keyboard_type=ft.KeyboardType.NUMBER, border_radius=8, expand=True)
        stock_tf = ft.TextField(label="库存", value=str(item.get('stock_quantity', 999) if is_edit else 999),
                                keyboard_type=ft.KeyboardType.NUMBER, border_radius=8, expand=True)
        status_dd = ft.Dropdown(label="状态", value=str(item.get('status', 1) if is_edit else 1),
                                options=[_opt(k, v) for k, v in STATUS_NAMES.items()],
                                border_radius=8, expand=True)
        level_tf = ft.TextField(label="兑换等级限制", value=str(item.get('change_level', 0) if is_edit else 0),
                                keyboard_type=ft.KeyboardType.NUMBER, border_radius=8, expand=True)

        controls = [name_tf, cat_dd, desc_tf, points_tf, time_field, stock_tf, status_dd, level_tf]

        def do_submit(e):
            name = name_tf.value.strip()
            if not name:
                self.snack("商品名称不能为空")
                return
            cat_id = int(cat_dd.value or 1)
            status_id = int(status_dd.value or 1)
            params = {
                'name': name, 'category': cat_id,
                'description': desc_tf.value or "",
                'points_required': int(points_tf.value or 0),
                'time_score': int(time_field.value or 0) if cat_id == 1 else 0,
                'stock_quantity': int(stock_tf.value or 0),
                'status': status_id,
                'change_level': int(level_tf.value or 0),
            }
            self._close_dialog(dlg)

            def do_save():
                if is_edit:
                    sets = ", ".join(f"{k}=?" for k in params)
                    self.db.execute(f"UPDATE exchange_items SET {sets} WHERE id=?", list(params.values()) + [item['id']])
                    before = {k: item.get(k) for k in params}
                    self._log_operation("edit_exchange", "exchange_item", target_id=item['id'],
                                        target_name=name, details=f"分类:{cat_id}",
                                        before_state=before, after_state=params)
                else:
                    cols = ", ".join(params.keys())
                    ph = ", ".join("?" for _ in params)
                    self.db.execute(f"INSERT INTO exchange_items ({cols}) VALUES ({ph})", list(params.values()))
                    self._log_operation("add_exchange", "exchange_item", target_name=name,
                                        details=f"分类:{cat_id},积分:{params['points_required']}",
                                        after_state=params)

            self.run_save_async(do_save, after_fn=lambda: self.page.run_task(self._load_items))

        dlg = ft.AlertDialog(
            title=ft.Text("编辑商品" if is_edit else "添加商品", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column(controls, spacing=8, scroll=ft.ScrollMode.ADAPTIVE),
                                 width=400, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_submit,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)

    def _delete_item(self, item):
        self.confirm_and_run("删除商品", f"确定删除「{item.get('name','')}」吗？",
                             self._do_delete, item['id'],
                             success_msg="已删除", loading_msg="删除中...")

    async def _do_delete(self, item_id):
        self.db.execute("DELETE FROM exchange_items WHERE id=?", [item_id])
        self._log_operation("delete_exchange", "exchange_item", target_id=item_id)
        await self._load_items()
