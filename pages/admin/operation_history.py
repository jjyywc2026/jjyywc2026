# pages/admin/operation_history.py
import flet as ft
import json as _json
from .base import AdminBaseTab

PAGE_SIZE = 20
INITIAL_LIMIT = 20

# 操作类型中文名+颜色
TYPE_META = {
    'use':             {'name': '使用',     'color': '#43A047', 'icon': ft.Icons.PLAY_ARROW},
    'use_coupon':      {'name': '使用卡券', 'color': '#00897B', 'icon': ft.Icons.CONFIRMATION_NUMBER},
    'exchange':        {'name': '兑换',     'color': '#FB8C00', 'icon': ft.Icons.SWAP_HORIZ},
    'open_gift':       {'name': '开启礼包', 'color': '#EC407A', 'icon': ft.Icons.CARD_GIFTCARD},
    'open_gift_extra': {'name': '额外掉落', 'color': '#AB47BC', 'icon': ft.Icons.AUTO_AWESOME},
    'synthesize':      {'name': '合成',     'color': '#8E24AA', 'icon': ft.Icons.BUILD},
    'admin_delete':    {'name': '管理员删除','color': '#E53935', 'icon': ft.Icons.DELETE},
    'admin_edit':      {'name': '管理员修改','color': '#1565C0', 'icon': ft.Icons.EDIT},
}

ALL_TYPES = [k for k in TYPE_META.keys() if k != 'open_gift_extra']


class OperationHistoryTab(AdminBaseTab):
    """用户物品操作历史（详细显示，分页加载）"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._user_tf = None
        self._type_dd = None
        self._current_uid = None
        self._current_type = "全部"
        self._loaded = 0
        self._has_more = True
        self._search_ring = None

    def build(self):
        self._user_tf = ft.TextField(hint_text="用户ID(留空查全部)",
                                      prefix_icon=ft.Icons.PERSON, expand=True,
                                      border_radius=8, height=34, dense=True,
                                      text_size=12,
                                      content_padding=ft.padding.symmetric(horizontal=10, vertical=0),
                                      keyboard_type=ft.KeyboardType.NUMBER)
        type_opts = [ft.dropdown.Option("全部")] + [ft.dropdown.Option(t) for t in ALL_TYPES]
        self._type_dd = ft.Dropdown(
            hint_text="操作类型", width=130, border_radius=8, value="全部",
            text_size=11, content_padding=ft.padding.symmetric(horizontal=8, vertical=0),
            options=type_opts)
        self._search_ring = ft.ProgressRing(width=16, height=16, color=ft.Colors.BLUE_400, visible=False)
        btn = ft.IconButton(
            ft.Icons.SEARCH, icon_size=18, tooltip="查询",
            on_click=lambda e: self._do_search(),
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE,
                                 shape=ft.RoundedRectangleBorder(radius=8),
                                 padding=ft.padding.all(7)),
        )
        self._list_view = ft.ListView(spacing=3, expand=True)
        return ft.Column([
            ft.Row([self._user_tf, self._type_dd, self._search_ring, btn], spacing=6,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self._list_view,
        ], spacing=4, expand=True)

    async def load_data(self):
        await self._reload(None, "全部")

    def _do_search(self):
        uid = None
        if self._user_tf.value and self._user_tf.value.strip():
            try:
                uid = int(self._user_tf.value.strip())
            except ValueError:
                self.snack("请输入有效的用户ID")
                return
        self._search_ring.visible = True
        try:
            if self._search_ring.page is not None:
                self._search_ring.update()
        except Exception:
            pass
        self.page.run_task(self._reload, uid, self._type_dd.value)

    def _build_sql(self, user_id, op_type, limit, offset=None):
        where = "WHERE operation_type != 'admin_grant'"
        params = []
        if user_id:
            where += " AND user_id=?"
            params.append(user_id)
        if op_type and op_type != "全部":
            where += " AND operation_type=?"
            params.append(op_type)
        if offset is not None:
            params.extend([limit, offset])
        else:
            params.append(limit)
        limit_clause = "LIMIT ? OFFSET ?" if offset is not None else "LIMIT ?"
        sql = f"""SELECT ioh.*, u.username,
                         i.name as item_name, i.quality as item_quality, i.category as item_category,
                         ti.name as target_item_name, ti.quality as target_quality, ti.category as target_category
                  FROM (SELECT * FROM item_operation_history {where} ORDER BY operation_time DESC {limit_clause}) ioh
                  LEFT JOIN users u ON ioh.user_id=u.user_id
                  LEFT JOIN items i ON ioh.item_id=i.id
                  LEFT JOIN items ti ON ioh.target_item_id=ti.id
                  ORDER BY ioh.operation_time DESC"""
        return sql, params

    async def _reload(self, user_id, op_type):
        import asyncio
        await asyncio.sleep(0.05)
        self._current_uid = user_id
        self._current_type = op_type
        self._loaded = 0
        self._has_more = True

        def _query():
            try:
                sql, params = self._build_sql(user_id, op_type, INITIAL_LIMIT)
                return self.db.fetch_all(sql, params), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            self._search_ring.visible = False
            return
        self._loaded = len(rows or [])
        self._has_more = self._loaded >= INITIAL_LIMIT
        self._render_rows(rows, replace=True)
        self._search_ring.visible = False
        try:
            if self._search_ring.page is not None:
                self._search_ring.update()
        except Exception:
            pass

    async def _load_more(self):
        import asyncio
        if not self._has_more:
            return
        await asyncio.sleep(0.05)
        offset = self._loaded
        user_id = self._current_uid
        op_type = self._current_type

        def _query():
            try:
                sql, params = self._build_sql(user_id, op_type, PAGE_SIZE, offset)
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
            if len(rows) < PAGE_SIZE:
                self._has_more = False
        self._render_rows(rows, replace=False)

    def _parse_details(self, details):
        """解析details JSON，返回字典"""
        if not details:
            return {}
        details = str(details).strip()
        if not (details.startswith('{') or details.startswith('[')):
            return {'_raw': details}
        try:
            return _json.loads(details)
        except Exception:
            return {'_raw': details}

    def _quality_color(self, quality):
        return self.QUALITY_COLORS.get(quality, '#9E9E9E') if quality else '#9E9E9E'

    def _item_chip(self, name, quality, quantity, prefix=""):
        """物品标签：名称(品质色) + 数量"""
        if not name:
            return None
        qcolor = self._quality_color(quality)
        parts = []
        if prefix:
            parts.append(ft.Text(prefix, size=10, color=ft.Colors.GREY_500))
        if quantity and quantity != 1:
            parts.append(ft.Text(f"{quantity}×", size=10, color=ft.Colors.GREY_700, weight=ft.FontWeight.W_600))
        parts.append(ft.Text(name, size=11, color=qcolor, weight=ft.FontWeight.W_700))
        if quality:
            parts.append(ft.Container(
                content=ft.Text(quality, size=8, color="white", weight=ft.FontWeight.BOLD),
                bgcolor=qcolor, border_radius=3,
                padding=ft.padding.symmetric(horizontal=3, vertical=0),
                margin=ft.margin.only(left=2)))
        return ft.Row(parts, spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True)

    def _render_rows(self, rows, replace=False):
        # ---- 预处理：把 open_gift_extra 合并到对应的 open_gift ----
        # 按 (user_id, item_id, 日期) 收集额外掉落
        extra_map = {}
        for r in rows or []:
            if r.get('operation_type') == 'open_gift_extra':
                key = (r.get('user_id'), r.get('item_id'), str(r.get('operation_time', ''))[:10])
                extra_map.setdefault(key, []).append(r)

        tiles = []
        for r in rows or []:
            op_type = r.get('operation_type', '')
            # 跳过独立的额外掉落记录（已合并到开启礼包）
            if op_type == 'open_gift_extra':
                continue

            meta = TYPE_META.get(op_type, {'name': op_type, 'color': '#757575', 'icon': ft.Icons.FIBER_MANUAL_RECORD})
            tname = meta['name']
            tcolor = meta['color']
            ticon = meta['icon']

            det = self._parse_details(r.get('details', ''))
            username = r.get('username', '?')
            op_id = r.get('operation_id', '')
            time_str = str(r.get('operation_time', ''))[:19]

            # 源物品
            src_name = r.get('item_name') or det.get('source_item_name') or f"物品{r.get('item_id','')}"
            src_q = r.get('item_quality') or det.get('source_quality') or det.get('source_item_quality')
            src_qty = r.get('quantity', '')
            src_cat = r.get('item_category') or det.get('source_item_category')

            # 目标物品
            tgt_name = r.get('target_item_name') or det.get('target_item_name')
            tgt_q = r.get('target_quality') or det.get('target_quality')
            tgt_qty = r.get('target_quantity') or det.get('target_quantity')

            # 构建描述行
            desc_rows = []

            # 第一行：源物品
            src_chip = self._item_chip(src_name, src_q, src_qty)
            if src_chip:
                desc_rows.append(src_chip)

            # 开启礼包：主掉落 + 额外掉落合并显示
            if op_type == 'open_gift':
                # 主掉落
                drops = []
                if tgt_name:
                    drops.append((tgt_name, tgt_q, tgt_qty, False))
                # 查找合并的额外掉落
                key = (r.get('user_id'), r.get('item_id'), str(r.get('operation_time', ''))[:10])
                extras = extra_map.get(key, [])
                for ex in extras:
                    ex_det = self._parse_details(ex.get('details', ''))
                    ex_name = ex.get('target_item_name') or ex_det.get('target_item_name')
                    ex_q = ex.get('target_quality') or ex_det.get('target_quality')
                    ex_qty = ex.get('target_quantity') or ex_det.get('target_quantity')
                    if ex_name:
                        drops.append((ex_name, ex_q, ex_qty, True))

                if drops:
                    arrow = ft.Row([ft.Icon(ft.Icons.ARROW_FORWARD, size=12, color=ft.Colors.GREY_400)],
                                   alignment=ft.MainAxisAlignment.CENTER)
                    desc_rows.append(arrow)
                    for dname, dq, dqty, is_extra in drops:
                        prefix = "额外 " if is_extra else "获得 "
                        chip = self._item_chip(dname, dq, dqty, prefix=prefix)
                        if chip:
                            desc_rows.append(chip)
                    if extras:
                        desc_rows.append(ft.Text(
                            f"共{len(drops)}个掉落（含{len(extras)}个额外）", size=9, color='#AB47BC', weight=ft.FontWeight.W_600))
            elif tgt_name:
                arrow = ft.Row([ft.Icon(ft.Icons.ARROW_FORWARD, size=12, color=ft.Colors.GREY_400)],
                               alignment=ft.MainAxisAlignment.CENTER)
                tgt_chip = self._item_chip(tgt_name, tgt_q, tgt_qty, prefix="获得 ")
                desc_rows.append(arrow)
                desc_rows.append(tgt_chip)

            # 额外信息行
            extra_parts = []
            if det.get('reward_type'):
                rt = det['reward_type']
                rv = det.get('reward_value', 0)
                reward_label = {'score': '积分', 'exp': '经验', 'lottery': '抽奖', 'star': '星星', 'time': '分钟'}.get(rt, rt)
                extra_parts.append(ft.Text(f"+{rv}{reward_label}", size=10, color='#2E7D32', weight=ft.FontWeight.W_600))
            if det.get('updated_points') is not None:
                extra_parts.append(ft.Text(f"余额:{det['updated_points']}", size=9, color=ft.Colors.GREY_500))
            if det.get('updated_stars') is not None:
                extra_parts.append(ft.Text(f"星星:{det['updated_stars']}", size=9, color=ft.Colors.GREY_500))
            if det.get('coin_count'):
                extra_parts.append(ft.Text(f"消耗{det['coin_count']}金币", size=10, color='#F57C00'))
            if det.get('chest_quality'):
                extra_parts.append(ft.Text(f"宝箱:{det['chest_quality']}", size=10,
                                           color=self._quality_color(det['chest_quality']), weight=ft.FontWeight.W_600))
            if det.get('source_quality') and det.get('target_quality'):
                extra_parts.append(ft.Text(
                    f"{det['source_quality']}→{det['target_quality']}", size=10,
                    color=self._quality_color(det['target_quality']), weight=ft.FontWeight.W_600))
            if op_type == 'admin_grant':
                extra_parts.append(ft.Text(det.get('_raw', '管理员发放'), size=10, color='#1976D2'))
            if op_type == 'admin_delete':
                extra_parts.append(ft.Text(det.get('_raw', '管理员删除'), size=10, color='#E53935'))
            if op_type == 'admin_edit':
                extra_parts.append(ft.Text(det.get('_raw', r.get('details', '')), size=10, color=ft.Colors.GREY_600))

            if extra_parts:
                desc_rows.append(ft.Row(extra_parts, spacing=6, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER))

            if not tgt_name and not extra_parts and det.get('_raw') and op_type != 'open_gift':
                desc_rows.append(ft.Text(det['_raw'], size=10, color=ft.Colors.GREY_500))

            # 头部
            header = ft.Row([
                ft.Container(content=ft.Icon(ticon, size=12, color=ft.Colors.WHITE),
                    bgcolor=tcolor, border_radius=4, width=20, height=20, alignment=ft.alignment.center),
                ft.Text(username, size=11, color=ft.Colors.GREY_700, weight=ft.FontWeight.W_600),
                ft.Container(content=ft.Text(tname, size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor=tcolor, border_radius=3, padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                ft.Container(expand=True),
                ft.Text(f"#{op_id}", size=9, color=ft.Colors.GREY_400),
            ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)

            # 底部
            footer = ft.Row([
                ft.Icon(ft.Icons.SCHEDULE, size=10, color=ft.Colors.GREY_400),
                ft.Text(time_str, size=10, color=ft.Colors.GREY_400),
                ft.Container(expand=True),
                ft.Text(f"UID:{r.get('user_id','')}", size=9, color=ft.Colors.GREY_300),
            ], spacing=3, vertical_alignment=ft.CrossAxisAlignment.CENTER)

            # 合并后的完整数据（用于详情弹窗）
            full_detail = dict(det)
            if op_type == 'open_gift':
                key = (r.get('user_id'), r.get('item_id'), str(r.get('operation_time', ''))[:10])
                extras = extra_map.get(key, [])
                if extras:
                    extra_list = []
                    for ex in extras:
                        ex_det = self._parse_details(ex.get('details', ''))
                        extra_list.append({
                            'operation_id': ex.get('operation_id'),
                            '掉落物品': ex.get('target_item_name') or ex_det.get('target_item_name'),
                            '品质': ex.get('target_quality') or ex_det.get('target_quality'),
                            '数量': ex.get('target_quantity') or ex_det.get('target_quantity'),
                            '掉落序号': f"{ex_det.get('drop_index','?')}/{ex_det.get('total_drops','?')}",
                        })
                    full_detail['_extra_drops'] = extra_list

            card = ft.Container(
                content=ft.Column([header] + desc_rows + [footer], spacing=3, tight=True),
                padding=ft.padding.symmetric(horizontal=10, vertical=7),
                bgcolor=ft.Colors.WHITE, border_radius=8,
                margin=ft.margin.only(bottom=3),
                border=ft.border.all(0.5, ft.Colors.with_opacity(0.1, tcolor)),
                shadow=ft.BoxShadow(blur_radius=2, color="#08000000", offset=ft.Offset(0, 1)),
                on_click=lambda e, d=full_detail, row=r: self._show_detail(d, row),
                ink=True,
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
            self._list_view.controls.append(self._empty("暂无操作记录"))
        self.page.update()

    def _show_detail(self, det, row=None):
        """点击卡片显示映射后的易读详情"""
        # 字段中文名映射
        FIELD_MAP = {
            'source_item_name': '来源物品', 'source_item_id': '来源物品ID',
            'source_item_quality': '来源品质', 'source_item_category': '来源分类',
            'source_quality': '来源品质',
            'target_item_name': '目标物品', 'target_item_id': '目标物品ID',
            'target_quality': '目标品质', 'target_item_category': '目标分类',
            'target_quantity': '目标数量',
            'reward_type': '奖励类型', 'reward_value': '奖励数值',
            'updated_points': '更新后积分', 'updated_stars': '更新后星星',
            'coin_count': '消耗金币', 'chest_quality': '宝箱品质',
            'drop_index': '掉落序号', 'total_drops': '总掉落数',
            'is_extra_drop': '是否额外掉落', 'operation_time': '操作时间',
            'quantity': '数量',
        }
        REWARD_MAP = {'score': '积分', 'exp': '经验', 'lottery': '抽奖次数', 'star': '星星', 'time': '分钟'}

        lines = []
        # 基础信息（来自row）
        if row:
            op_type = row.get('operation_type', '')
            meta = TYPE_META.get(op_type, {'name': op_type})
            lines.append(("操作类型", meta['name']))
            lines.append(("操作ID", str(row.get('operation_id', ''))))
            lines.append(("用户", row.get('username', '?')))
            lines.append(("用户ID", str(row.get('user_id', ''))))
            lines.append(("操作时间", str(row.get('operation_time', ''))[:19]))
            src_name = row.get('item_name') or det.get('source_item_name') or f"物品{row.get('item_id','')}"
            lines.append(("操作物品", src_name))
            if row.get('item_quality') or det.get('source_item_quality'):
                lines.append(("物品品质", row.get('item_quality') or det.get('source_item_quality')))
            lines.append(("物品数量", str(row.get('quantity', ''))))
            if row.get('target_item_name') or det.get('target_item_name'):
                lines.append(("获得物品", row.get('target_item_name') or det.get('target_item_name')))
                if row.get('target_quality') or det.get('target_quality'):
                    lines.append(("获得品质", row.get('target_quality') or det.get('target_quality')))
                if row.get('target_quantity') or det.get('target_quantity'):
                    lines.append(("获得数量", str(row.get('target_quantity') or det.get('target_quantity'))))
            lines.append(("---", "---"))

        # details 字段映射
        for k, v in det.items():
            if k == '_raw':
                lines.append(("备注", v))
                continue
            if k == '_extra_drops':
                continue
            label = FIELD_MAP.get(k, k)
            if k == 'reward_type' and v in REWARD_MAP:
                v = REWARD_MAP[v]
            if k == 'is_extra_drop':
                v = "是" if v else "否"
            lines.append((label, str(v)))

        # 额外掉落
        if det.get('_extra_drops'):
            lines.append(("---", "---"))
            lines.append(("额外掉落", f"共{len(det['_extra_drops'])}个"))
            for i, ex in enumerate(det['_extra_drops'], 1):
                lines.append((f"  额外{i}", f"{ex.get('掉落物品','?')} ×{ex.get('数量','?')} ({ex.get('品质','?')}) 序号{ex.get('掉落序号','?')}"))

        # 构建列表
        rows_ui = []
        for label, value in lines:
            if label == "---":
                rows_ui.append(ft.Divider(height=1, color=ft.Colors.GREY_200))
            else:
                rows_ui.append(ft.Row([
                    ft.Container(width=90, content=ft.Text(label, size=11, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_500)),
                    ft.Text(value, size=11, color=ft.Colors.GREY_800, weight=ft.FontWeight.W_600, selectable=True),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.START))

        dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Container(content=ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.WHITE),
                             bgcolor=ft.Colors.BLUE_600, border_radius=6, padding=4),
                ft.Text("操作详情", size=15, weight=ft.FontWeight.BOLD),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column(rows_ui, spacing=4, tight=True, scroll=ft.ScrollMode.ADAPTIVE),
                width=340, height=400, padding=8),
            actions=[ft.TextButton("关闭", on_click=lambda e: self._close_dialog(dlg))],
        )
        self.page.open(dlg)
