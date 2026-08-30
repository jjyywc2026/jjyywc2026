# pages/admin/item_management.py
import flet as ft
from .base import AdminBaseTab


# 分类图标映射
CATEGORY_ICONS = {
    '礼包': ft.Icons.CARD_GIFTCARD, '礼物': ft.Icons.CARD_GIFTCARD,
    '钥匙': ft.Icons.VPN_KEY, '钥匙道具': ft.Icons.VPN_KEY,
    '材料': ft.Icons.SETTINGS, '素材': ft.Icons.SETTINGS,
    '消耗品': ft.Icons.LOCAL_DRINK, '药水': ft.Icons.LOCAL_DRINK,
    '装备': ft.Icons.SHIELD, '武器': ft.Icons.COLORIZE,
    '特殊卡片': ft.Icons.STYLE, '卡片': ft.Icons.STYLE,
    '普通': ft.Icons.INVENTORY_2, '道具': ft.Icons.INVENTORY_2,
    '碎片': ft.Icons.EXTENSION, '宝石': ft.Icons.DIAMOND,
    '宠物': ft.Icons.PETS, '坐骑': ft.Icons.DIRECTIONS_BIKE,
    '称号': ft.Icons.MILITARY_TECH, '时装': ft.Icons.CHECKROOM,
    '货币': ft.Icons.PAYMENTS, '卡券': ft.Icons.CONFIRMATION_NUMBER,
    '宝箱': ft.Icons.INVENTORY,
}

# 品质渐变（从浅到深）
QUALITY_GRADIENTS = {
    '普通': ['#E0E0E0', '#9E9E9E'],
    '优秀': ['#C8E6C9', '#4CAF50'],
    '稀有': ['#BBDEFB', '#2196F3'],
    '史诗': ['#E1BEE7', '#9C27B0'],
    '传说': ['#FFE0B2', '#FF9800'],
    '神器': ['#FFCDD2', '#F44336'],
    '高级': ['#DCEDC8', '#8BC34A'],
    '神秘': ['#FFCDD2', '#D32F2F'],
    '传奇': ['#FFECB3', '#FFC107'],
}


def _category_icon(category):
    if not category:
        return ft.Icons.INVENTORY_2
    return CATEGORY_ICONS.get(category, CATEGORY_ICONS.get(str(category).strip(), ft.Icons.INVENTORY_2))


class ItemManagementTab(AdminBaseTab):
    """物品管理：增删改查"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._search_tf = None

    def build(self):
        search_row, self._search_tf = self._search_bar("搜索物品", "输入物品名称或ID", self._do_search)
        add_btn = ft.IconButton(
            ft.Icons.ADD, icon_size=22, tooltip="新增物品",
            on_click=self._add_item,
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 padding=ft.padding.all(8)),
        )
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([
            ft.Row([ft.Container(content=search_row, expand=True), add_btn], spacing=6,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self._list_view,
        ], spacing=4, expand=True)

    async def load_data(self):
        await self._load_items()

    def _do_search(self, keyword):
        self._search_loading_show(True)
        self.page.run_task(self._load_items, keyword)

    async def _load_items(self, keyword=None):
        import asyncio
        await asyncio.sleep(0.05)

        def _query():
            try:
                if keyword and keyword.strip():
                    kw = f"%{keyword.strip()}%"
                    return self.db.fetch_all(
                        "SELECT * FROM items WHERE name LIKE ? OR CAST(id AS TEXT) LIKE ? ORDER BY id",
                        [kw, kw]), None
                else:
                    return self.db.fetch_all("SELECT * FROM items ORDER BY category, id"), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            return
        tiles = []
        import os
        assets_dir = getattr(self.page, 'assets_dir', '') or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'assets')
        for r in rows or []:
            img_id = r.get('image_id') or ''
            quality = r.get('quality', '普通')
            q_color = self.QUALITY_COLORS.get(quality, "#9E9E9E")
            q_grad = QUALITY_GRADIENTS.get(quality, QUALITY_GRADIENTS['普通'])
            cat = r.get('category', '')
            cat_icon = _category_icon(cat)

            # 检查图片是否存在
            img_path = None
            if img_id:
                for ext in ('.png', '.jpg'):
                    p = os.path.join(assets_dir, f"{img_id}{ext}")
                    if os.path.exists(p):
                        img_path = f"{img_id}{ext}"
                        break

            if img_path:
                # 有图片：品质边框+阴影+圆角
                leading = ft.Container(
                    width=40, height=40, border_radius=8,
                    border=ft.border.all(2.5, q_color),
                    shadow=ft.BoxShadow(blur_radius=6, color=q_color + "60", offset=ft.Offset(0, 2)),
                    content=ft.Image(src=img_path, width=36, height=36, fit=ft.ImageFit.COVER,
                                      border_radius=ft.border_radius.all(5)),
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                )
            else:
                # 无图片：品质渐变背景+分类图标
                leading = ft.Container(
                    width=40, height=40, border_radius=8,
                    border=ft.border.all(2.5, q_color),
                    gradient=ft.LinearGradient(
                        begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                        colors=q_grad),
                    shadow=ft.BoxShadow(blur_radius=6, color=q_color + "60", offset=ft.Offset(0, 2)),
                    alignment=ft.alignment.center,
                    content=ft.Icon(cat_icon, color=ft.Colors.WHITE, size=20),
                )
            tiles.append(self._list_tile(
                leading,
                ft.Row([
                    ft.Text(f"{r['name']}", size=13, weight=ft.FontWeight.W_600, color=q_color),
                    self._quality_chip(quality),
                ], spacing=4),
                ft.Text(f"ID:{r['id']} · {cat} · 价值:{r.get('value',0)} · 堆叠:{r.get('max_stack','-')}",
                        size=10, color=ft.Colors.GREY_500),
                trailing=ft.IconButton(ft.Icons.DELETE, icon_size=16, icon_color=ft.Colors.RED_400,
                                       on_click=lambda e, item=r: self._delete_item(item)),
                on_click=lambda e, item=r: self._edit_item(item),
                leading_width=44,
            ))
        if not tiles:
            tiles.append(self._empty("暂无物品"))
        self._list_view.controls = tiles
        self._search_loading_show(False)
        self.page.update()

    def _add_item(self, e=None):
        self._open_form(None)

    def _edit_item(self, item):
        self._open_form(item)

    def _open_form(self, item):
        is_edit = item is not None
        # 分类从数据库获取（去重）
        try:
            cat_rows = self.db.fetch_all("SELECT DISTINCT category FROM items WHERE category IS NOT NULL AND category != '' ORDER BY category")
            categories = [r['category'] for r in (cat_rows or [])]
        except Exception:
            categories = []
        # 兜底常用分类
        for c in ["普通", "钥匙", "礼包", "材料", "消耗品", "装备", "特殊卡片"]:
            if c not in categories:
                categories.append(c)
        # 品质从数据库获取（去重）
        try:
            q_rows = self.db.fetch_all("SELECT DISTINCT quality FROM items WHERE quality IS NOT NULL AND quality != '' ORDER BY quality")
            qualities = [r['quality'] for r in (q_rows or [])]
        except Exception:
            qualities = ["普通", "高级", "稀有", "史诗", "传奇", "神秘"]

        fields = [
            ("物品名称", "name", item.get('name') if is_edit else "", "text"),
            ("分类", "category", item.get('category') if is_edit else (categories[0] if categories else "普通"),
             categories),
            ("品质", "quality", item.get('quality') if is_edit else "普通",
             qualities),
            ("图片ID", "image_id", item.get('image_id') if is_edit else "", "text"),
            ("价值", "value", item.get('value') if is_edit else 0, "number"),
            ("最大堆叠", "max_stack", item.get('max_stack') if is_edit else 99, "number"),
            ("描述", "description", item.get('description') if is_edit else "", "textarea"),
        ]

        def on_submit(data):
            try:
                name = data['name'].strip()
                if not name:
                    self.snack("物品名称不能为空")
                    return
                category = data['category'] or "普通"
                quality = data['quality'] or "普通"
                image_id = (data.get('image_id') or "").strip()
                value = int(data['value'] or 0)
                max_stack = int(data['max_stack'] or 99)
                desc = data['description'] or ""
                if is_edit:
                    self.db.execute(
                        """UPDATE items SET name=?, category=?, quality=?, image_id=?, value=?, max_stack=?, description=?
                           WHERE id=?""",
                        [name, category, quality, image_id, value, max_stack, desc, item['id']])
                    before = {k: item.get(k) for k in ['name','category','quality','image_id','value','max_stack','description']}
                    after = {'name': name, 'category': category, 'quality': quality,
                             'image_id': image_id, 'value': value, 'max_stack': max_stack, 'description': desc}
                    self._log_operation("edit_item", "item", target_id=item['id'],
                                        target_name=name, details=f"分类:{category}",
                                        before_state=before, after_state=after)
                    self.snack(f"已更新: {name}")
                else:
                    self.db.execute(
                        """INSERT INTO items (name, category, quality, image_id, value, stackable, max_stack, description)
                           VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                        [name, category, quality, image_id, value, max_stack, desc])
                    self._log_operation("add_item", "item", target_name=name,
                                        details=f"分类:{category},价值:{value}",
                                        after_state={'name': name, 'category': category, 'quality': quality,
                                                     'value': value, 'max_stack': max_stack})
                    self.snack(f"已新增: {name}")
                self.page.run_task(self._load_items)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        self.form_dialog("编辑物品" if is_edit else "新增物品", fields, on_submit)

    def _delete_item(self, item):
        self.confirm_and_run(
            "删除物品", f"确定删除「{item['name']}」(ID:{item['id']})吗？此操作不可恢复。",
            self._do_delete, item['id'],
            success_msg="已删除", loading_msg="删除中...")

    async def _do_delete(self, item_id):
        self.db.execute("DELETE FROM items WHERE id=?", [item_id])
        self._log_operation("delete_item", "item", target_id=item_id)
        await self._load_items()
