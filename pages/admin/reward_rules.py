# pages/admin/reward_rules.py
import flet as ft
import json
from .base import AdminBaseTab


class RewardRulesTab(AdminBaseTab):
    """奖励规则管理：增删改查"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None

    def build(self):
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([
            ft.Row([
                ft.Text("奖励规则", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800, expand=True),
                self._action_button("新增规则", ft.Icons.ADD, self._add_rule, ft.Colors.GREEN_600),
            ]),
            self._list_view,
        ], spacing=8, expand=True)

    async def load_data(self):
        await self._load_rules()

    async def _load_rules(self):
        import asyncio
        await asyncio.sleep(0.05)

        def _query():
            try:
                return self.db.fetch_all(
                    "SELECT * FROM reward_rules ORDER BY is_active DESC, priority, rule_id"), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            return
        type_names = {'score': '积分', 'experience': '经验', 'star': '星星',
                      'item': '物品', 'lottery': '抽奖次数'}
        tiles = []
        for r in rows or []:
            rt = type_names.get(r['reward_type'], r['reward_type'])
            if r['reward_type'] == 'item':
                reward_desc = f"物品ID:{r['item_id']} ×{r['item_quantity']}"
            else:
                reward_desc = f"{rt} +{r['reward_value']}"
            active = r.get('is_active', 0)
            tiles.append(self._list_tile(
                ft.Icon(ft.Icons.STAR if active else ft.Icons.STAR_BORDER,
                        color=ft.Colors.AMBER_500 if active else ft.Colors.GREY_400),
                ft.Text(f"{r['rule_name']}", size=12),
                ft.Text(f"{r.get('condition_type','')} · {reward_desc} · 每日限{r.get('daily_limit',0)}次",
                        size=10, color=ft.Colors.GREY_500),
                trailing=ft.Row([
                    ft.Switch(value=bool(active), on_change=lambda e, rid=r['rule_id']: self._toggle_active(rid, e.control.value)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=16, icon_color=ft.Colors.RED_400,
                                   on_click=lambda e, rule=r: self._delete_rule(rule)),
                ], spacing=0),
                on_click=lambda e, rule=r: self._edit_rule(rule),
            ))
        if not tiles:
            tiles.append(self._empty("暂无规则"))
        self._list_view.controls = tiles
        self.page.update()

    def _toggle_active(self, rule_id, active):
        try:
            self.db.execute("UPDATE reward_rules SET is_active=? WHERE rule_id=?", [1 if active else 0, rule_id])
            self.snack("已更新状态")
        except Exception as e:
            self.snack(f"更新失败: {e}")

    def _add_rule(self, e=None):
        self._open_form(None)

    def _edit_rule(self, rule):
        self._open_form(rule)

    def _open_form(self, rule):
        is_edit = rule is not None
        fields = [
            ("规则名称", "rule_name", rule.get('rule_name') if is_edit else "", "text"),
            ("规则描述", "rule_description", rule.get('rule_description') if is_edit else "", "textarea"),
            ("条件类型", "condition_type", rule.get('condition_type') if is_edit else "daily_login",
             ["daily_login", "correct_answer", "milestone", "level_up", "custom"]),
            ("奖励类型", "reward_type", rule.get('reward_type') if is_edit else "score",
             ["score", "experience", "star", "item", "lottery"]),
            ("奖励数值", "reward_value", rule.get('reward_value') if is_edit else 10, "number"),
            ("物品ID(物品奖励时)", "item_id", rule.get('item_id') if is_edit else "", "text"),
            ("物品数量", "item_quantity", rule.get('item_quantity') if is_edit else 1, "number"),
            ("每日限制", "daily_limit", rule.get('daily_limit') if is_edit else 1, "number"),
            ("总限制", "total_limit", rule.get('total_limit') if is_edit else 0, "number"),
            ("优先级", "priority", rule.get('priority') if is_edit else 0, "number"),
            ("冷却小时", "cooldown_hours", rule.get('cooldown_hours') if is_edit else 0, "number"),
        ]

        def on_submit(data):
            try:
                name = data['rule_name'].strip()
                if not name:
                    self.snack("规则名称不能为空")
                    return
                params = {
                    'rule_name': name,
                    'rule_description': data['rule_description'] or "",
                    'condition_type': data['condition_type'] or "custom",
                    'reward_type': data['reward_type'] or "score",
                    'reward_value': int(data['reward_value'] or 0),
                    'item_id': int(data['item_id']) if data['item_id'] else None,
                    'item_quantity': int(data['item_quantity'] or 1),
                    'daily_limit': int(data['daily_limit'] or 0),
                    'total_limit': int(data['total_limit'] or 0),
                    'priority': int(data['priority'] or 0),
                    'cooldown_hours': int(data['cooldown_hours'] or 0),
                    'condition_params': "{}",
                    'is_active': 1,
                    'repeatable': 1,
                }
                if is_edit:
                    sets = ", ".join(f"{k}=?" for k in params)
                    self.db.execute(f"UPDATE reward_rules SET {sets} WHERE rule_id=?",
                                    list(params.values()) + [rule['rule_id']])
                    self.snack(f"已更新: {name}")
                else:
                    cols = ", ".join(params.keys())
                    ph = ", ".join("?" for _ in params)
                    self.db.execute(f"INSERT INTO reward_rules ({cols}) VALUES ({ph})",
                                    list(params.values()))
                    self.snack(f"已新增: {name}")
                self.page.run_task(self._load_rules)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        self.form_dialog("编辑规则" if is_edit else "新增规则", fields, on_submit)

    def _delete_rule(self, rule):
        self.confirm_and_run("删除规则", f"确定删除「{rule['rule_name']}」吗？",
                             self._do_delete, rule['rule_id'],
                             success_msg="已删除", loading_msg="删除中...")

    async def _do_delete(self, rule_id):
        self.db.execute("DELETE FROM reward_rules WHERE rule_id=?", [rule_id])
        await self._load_rules()
