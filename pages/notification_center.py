# pages/notification_center.py
import flet as ft
import sqlite3
import json
from app_paths import get_app_dir

# 通知类型
TYPE_MAP = {
    'item': ('物品发放', ft.Icons.SHOPPING_BAG, ft.Colors.AMBER_600),
    'gift': ('礼包发放', ft.Icons.REDEEM, ft.Colors.PURPLE_600),
    'score': ('积分奖励', ft.Icons.STAR, ft.Colors.ORANGE_500),
    'time': ('时长奖励', ft.Icons.TIMER, ft.Colors.BLUE_500),
    'system': ('系统通知', ft.Icons.NOTIFICATIONS, ft.Colors.GREY_600),
}

# 品质颜色
QUALITY_COLORS = {
    '普通': '#9E9E9E', '优秀': '#4CAF50', '稀有': '#2196F3',
    '史诗': '#9C27B0', '传说': '#FF9800', '神器': '#F44336',
}


class NotificationCenter:
    """消息通知中心（奖励发放 + 系统通知）"""

    def __init__(self, page, user_data):
        self.page = page
        self.user_data = user_data
        self._list_view = None
        self._unread_count = 0
        self._read_ids = self._load_read_ids()

    def _load_read_ids(self):
        try:
            f = get_app_dir() / "notif_read.json"
            if f.exists():
                return set(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
        return set()

    def _save_read_ids(self):
        try:
            f = get_app_dir() / "notif_read.json"
            f.write_text(json.dumps(list(self._read_ids)), encoding="utf-8")
        except Exception:
            pass

    def _get_notifications(self):
        """获取通知列表（奖励发放记录 + 系统通知）"""
        uid = self.user_data.get("id") or self.user_data.get("user_id")
        notifs = []
        try:
            db_path = get_app_dir() / "local_cache.db"
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            # 奖励发放记录
            try:
                rows = conn.execute(
                    """SELECT rh.id, rh.reward_type, rh.item_id, rh.item_quantity,
                              rh.reward_value, rh.rule_id, rh.milestone_number,
                              rh.created_at, rh.admin_name, i.name as item_name,
                              i.quality as item_quality
                       FROM reward_histories rh
                       LEFT JOIN items i ON rh.item_id=i.id
                       WHERE rh.user_id=?
                       ORDER BY rh.created_at DESC LIMIT 100""",
                    [uid]
                ).fetchall()
                for r in rows:
                    rtype = r['reward_type']
                    tinfo = TYPE_MAP.get(rtype, TYPE_MAP['system'])
                    if rtype in ('item', 'gift'):
                        iname = r['item_name'] or f"物品#{r['item_id']}"
                        q = r['item_quality']
                        qcolor = QUALITY_COLORS.get(q, '#757575') if q else '#757575'
                        title = f"{tinfo[0]}：{iname} ×{r['item_quantity']}"
                        desc = f"{r['admin_name'] or '系统'}发放"
                        color = qcolor
                    elif rtype == 'score':
                        title = f"{tinfo[0]}：+{r['reward_value']}积分"
                        desc = f"里程碑 #{r['milestone_number']}" if r['milestone_number'] else "系统奖励"
                        color = tinfo[2]
                    elif rtype == 'time':
                        mins = r['reward_value'] or 0
                        title = f"{tinfo[0]}：+{mins}分钟"
                        desc = f"里程碑 #{r['milestone_number']}" if r['milestone_number'] else "系统奖励"
                        color = tinfo[2]
                    else:
                        title = tinfo[0]
                        desc = str(r['reward_value'] or '')
                        color = tinfo[2]
                    notifs.append({
                        'id': f"reward_{r['id']}",
                        'type': rtype,
                        'icon': tinfo[1],
                        'color': color,
                        'title': title,
                        'desc': desc,
                        'time': r['created_at'] or '',
                    })
            except Exception:
                pass
            conn.close()
        except Exception:
            pass
        # 系统通知（如果有 notifications 表）
        try:
            db_path = get_app_dir() / "local_cache.db"
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT * FROM notifications WHERE user_id=? OR user_id IS NULL "
                    "ORDER BY created_at DESC LIMIT 20", [uid]
                ).fetchall()
                for r in rows:
                    notifs.append({
                        'id': f"sys_{r['id']}",
                        'type': 'system',
                        'icon': ft.Icons.NOTIFICATIONS,
                        'color': ft.Colors.GREY_600,
                        'title': r.get('title', '系统通知'),
                        'desc': r.get('content', ''),
                        'time': r.get('created_at', ''),
                    })
            except Exception:
                pass
            conn.close()
        except Exception:
            pass
        # 按时间排序
        notifs.sort(key=lambda x: x['time'], reverse=True)
        return notifs

    def get_unread_count(self):
        """获取未读通知数"""
        notifs = self._get_notifications()
        return sum(1 for n in notifs if n['id'] not in self._read_ids)

    def build(self):
        self._list_view = ft.ListView(spacing=6, expand=True, padding=ft.padding.all(12))
        self._render()
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("消息通知", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                    ft.Container(expand=True),
                    ft.TextButton("全部已读", icon=ft.Icons.DONE_ALL,
                                  on_click=lambda e: self._mark_all_read()),
                ], spacing=4),
                ft.Container(height=1, bgcolor=ft.Colors.GREY_200),
                self._list_view,
            ], spacing=8, expand=True),
            expand=True, padding=16,
            bgcolor=ft.Colors.TRANSPARENT,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[ft.Colors.BLUE_50, ft.Colors.PURPLE_50],
            ),
        )

    def _render(self):
        notifs = self._get_notifications()
        tiles = []
        for n in notifs:
            is_read = n['id'] in self._read_ids
            dot = ft.Container(width=8, height=8, border_radius=4,
                               bgcolor=ft.Colors.RED_500) if not is_read else ft.Container(width=8)
            tiles.append(ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Icon(n['icon'], size=20, color=ft.Colors.WHITE),
                        width=40, height=40, border_radius=20, bgcolor=n['color'],
                        alignment=ft.alignment.center,
                    ),
                    ft.Container(width=10),
                    ft.Column([
                        ft.Row([
                            ft.Text(n['title'], size=13, weight=ft.FontWeight.W_600,
                                    color=ft.Colors.GREY_800),
                            dot,
                        ], spacing=6, tight=True),
                        ft.Text(n['desc'], size=11, color=ft.Colors.GREY_500),
                        ft.Text(n['time'], size=9, color=ft.Colors.GREY_400),
                    ], spacing=2, tight=True, expand=True),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START),
                bgcolor=ft.Colors.WHITE, border_radius=12, padding=12,
                shadow=ft.BoxShadow(blur_radius=4, color="#08000000", offset=ft.Offset(0, 1)),
                on_click=lambda e, nid=n['id']: self._mark_read(nid),
            ))
        if not tiles:
            tiles.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.INBOX, size=48, color=ft.Colors.GREY_300),
                    ft.Text("暂无通知", size=14, color=ft.Colors.GREY_400),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                padding=60, alignment=ft.alignment.center,
            ))
        self._list_view.controls = tiles
        try:
            self.page.update()
        except Exception:
            pass

    def _mark_read(self, nid):
        self._read_ids.add(nid)
        self._save_read_ids()
        self._render()

    def _mark_all_read(self):
        notifs = self._get_notifications()
        for n in notifs:
            self._read_ids.add(n['id'])
        self._save_read_ids()
        self._render()
