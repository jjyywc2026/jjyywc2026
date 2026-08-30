# pages/admin/backpack.py
import flet as ft
from .base import AdminBaseTab


class BackpackTab(AdminBaseTab):
    """用户背包管理：查看、修改数量、删除物品"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._user_tf = None
        self._current_uid = None

    def build(self):
        search_row, self._user_tf = self._search_bar("用户ID", "输入用户ID查询背包", self._do_search)
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([search_row, self._list_view], spacing=4, expand=True)

    async def load_data(self):
        """刷新：重新加载当前用户的背包"""
        if self._current_uid is not None:
            await self._load_backpack(self._current_uid)

    def _do_search(self, keyword):
        try:
            uid = int(keyword.strip())
        except (ValueError, AttributeError):
            self.snack("请输入有效的用户ID")
            return
        self._current_uid = uid
        self._search_loading_show(True)
        self.page.run_task(self._load_backpack, uid)

    async def _load_backpack(self, user_id):
        import asyncio
        await asyncio.sleep(0.05)

        def _query():
            try:
                return self.db.fetch_all(
                    """SELECT ui.id, ui.item_id, ui.quantity, i.name, i.category, i.quality
                       FROM user_items ui
                       LEFT JOIN items i ON ui.item_id = i.id
                       WHERE ui.user_id=? AND ui.quantity > 0 ORDER BY ui.quantity DESC""",
                    [user_id]), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            return
        tiles = []
        for r in rows or []:
            quality = r.get('quality', '普通')
            q_color = self.QUALITY_COLORS.get(quality, "#9E9E9E")
            tiles.append(self._list_tile(
                ft.Container(
                    width=32, height=32, border_radius=6, bgcolor=q_color,
                    alignment=ft.alignment.center,
                    content=ft.Icon(ft.Icons.INVENTORY, color=ft.Colors.WHITE, size=16),
                ),
                ft.Row([
                    ft.Text(f"{r.get('name', '物品' + str(r['item_id']))}", size=12, weight=ft.FontWeight.W_600, color=q_color),
                    self._quality_chip(quality),
                ], spacing=4),
                ft.Text(f"ID:{r['item_id']} · {r.get('category','')} · 数量:{r['quantity']}",
                        size=10, color=ft.Colors.GREY_500),
                trailing=ft.Row([
                    ft.IconButton(ft.Icons.EDIT, icon_size=18,
                                   on_click=lambda e, item=r, uid=user_id: self._edit_qty(uid, item)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=18, icon_color=ft.Colors.RED_400,
                                   on_click=lambda e, item=r, uid=user_id: self._delete_item(uid, item)),
                ], spacing=0),
            ))
        if not tiles:
            tiles.append(self._empty("该用户背包为空"))
        self._list_view.controls = tiles
        self._search_loading_show(False)
        self.page.update()

    def _edit_qty(self, user_id, item):
        fields = [("物品", "item_name", f"{item.get('name','')} (ID:{item['item_id']})", "text"),
                  ("当前数量", "old_qty", item['quantity'], "number"),
                  ("新数量", "new_qty", item['quantity'], "number")]

        def on_submit(data):
            try:
                new_qty = int(data['new_qty'])
                if new_qty < 0:
                    self.snack("数量不能为负")
                    return
                ok, msg = self.reward_svc.update_backpack_item(user_id, item['item_id'], new_qty)
                self.snack(msg if ok else f"失败: {msg}")
                if ok:
                    self.page.run_task(self._load_backpack, user_id)
            except Exception as ex:
                self.snack(f"修改失败: {ex}")

        self.form_dialog("修改数量", fields, on_submit)

    def _delete_item(self, user_id, item):
        self.confirm_and_run("移除物品",
                             f"确定从用户 {user_id} 背包移除「{item.get('name','')}」吗？",
                             self._do_delete, user_id, item['item_id'],
                             success_msg="已移除", loading_msg="移除中...")

    async def _do_delete(self, user_id, item_id):
        ok, msg = self.reward_svc.delete_backpack_item(user_id, item_id)
        if not ok:
            raise Exception(msg)
        await self._load_backpack(user_id)
