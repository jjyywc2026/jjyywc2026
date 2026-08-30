# pages/notification_center.py
import flet as ft
import json
from app_paths import get_app_dir

# 消息类型 → (显示名, 图标, 颜色)
TYPE_MAP = {
    'announcement': ('系统公告', ft.Icons.CAMPAIGN, ft.Colors.BLUE_600),
    'system': ('系统通知', ft.Icons.NOTIFICATIONS, ft.Colors.GREY_600),
    'reward': ('奖励通知', ft.Icons.CARD_GIFTCARD, ft.Colors.ORANGE_600),
    'warning': ('警告提醒', ft.Icons.WARNING, ft.Colors.RED_600),
    'activity': ('活动通知', ft.Icons.EVENT, ft.Colors.GREEN_600),
    'gift': ('礼包发放', ft.Icons.REDEEM, ft.Colors.PURPLE_600),
    'levelup': ('等级提升', ft.Icons.TRENDING_UP, ft.Colors.AMBER_600),
    'backpack': ('背包变更', ft.Icons.BACKPACK, ft.Colors.TEAL_600),
    'timelimit': ('时间限制', ft.Icons.TIMER, ft.Colors.INDIGO_600),
    'card': ('赋能卡', ft.Icons.CONFIRMATION_NUMBER, ft.Colors.PINK_600),
    'task': ('任务变更', ft.Icons.TASK_ALT, ft.Colors.CYAN_600),
}


class NotificationCenter:
    """消息通知中心（读取 user_messages 表）"""

    def __init__(self, page, user_data):
        self.page = page
        self.user_data = user_data
        self._list_view = None
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

    def _get_messages(self):
        """从云端 user_messages 表获取当前用户的消息"""
        uid = self.user_data.get("id") or self.user_data.get("user_id")
        messages = []
        try:
            db = getattr(self.page, '_db', None)
            if db is None:
                return messages
            rows = db.fetch_all(
                """SELECT id, user_id, title, content, message_type, created_at
                   FROM user_messages
                   WHERE user_id = ?
                   ORDER BY created_at DESC LIMIT 100""",
                [uid]
            )
            for r in (rows or []):
                mtype = r.get('message_type', 'system')
                tinfo = TYPE_MAP.get(mtype, TYPE_MAP['system'])
                mid = r.get('id', 0)
                messages.append({
                    'id': f"msg_{mid}",
                    'type': mtype,
                    'type_name': tinfo[0],
                    'icon': tinfo[1],
                    'color': tinfo[2],
                    'title': r.get('title', ''),
                    'content': r.get('content', '') or '',
                    'time': str(r.get('created_at', ''))[:19],
                })
        except Exception as e:
            print(f"[notification] 获取消息失败: {e}")
        return messages

    def get_unread_count(self):
        """获取未读消息数"""
        messages = self._get_messages()
        return sum(1 for m in messages if m['id'] not in self._read_ids)

    def build(self):
        self._list_view = ft.ListView(spacing=6, expand=True, padding=ft.padding.all(12))
        self._render()
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.MAIL, size=22, color=ft.Colors.BLUE_700),
                    ft.Text("消息通知", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                    ft.Container(expand=True),
                    ft.TextButton("全部已读", icon=ft.Icons.DONE_ALL,
                                  on_click=lambda e: self._mark_all_read()),
                ], spacing=6),
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
        messages = self._get_messages()
        tiles = []
        for m in messages:
            is_read = m['id'] in self._read_ids
            # 未读红点
            dot = ft.Container(width=8, height=8, border_radius=4,
                               bgcolor=ft.Colors.RED_500) if not is_read else ft.Container(width=8)
            # 类型标签
            type_tag = ft.Container(
                content=ft.Text(m['type_name'], size=9, color=ft.Colors.WHITE,
                                weight=ft.FontWeight.W_700),
                bgcolor=m['color'],
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=1),
            )
            # 内容（多行，截断）
            content_lines = m['content'].split('\n')
            content_text = '\n'.join(content_lines[:4])
            if len(content_lines) > 4:
                content_text += '\n...'

            tiles.append(ft.Container(
                content=ft.Row([
                    # 左侧图标圆
                    ft.Container(
                        content=ft.Icon(m['icon'], size=20, color=ft.Colors.WHITE),
                        width=40, height=40, border_radius=20, bgcolor=m['color'],
                        alignment=ft.alignment.center,
                    ),
                    ft.Container(width=10),
                    # 右侧内容
                    ft.Column([
                        ft.Row([
                            type_tag,
                            ft.Text(m['title'], size=13, weight=ft.FontWeight.W_700,
                                    color=ft.Colors.GREY_800, expand=True),
                            dot,
                        ], spacing=6, tight=True),
                        ft.Text(content_text, size=11, color=ft.Colors.GREY_600,
                                selectable=True),
                        ft.Text(m['time'], size=9, color=ft.Colors.GREY_400),
                    ], spacing=2, tight=True, expand=True),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START),
                bgcolor=ft.Colors.WHITE, border_radius=12, padding=12,
                shadow=ft.BoxShadow(blur_radius=4, color="#08000000", offset=ft.Offset(0, 1)),
                on_click=lambda e, mid=m['id']: self._mark_read(mid),
            ))
        if not tiles:
            tiles.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.INBOX, size=48, color=ft.Colors.GREY_300),
                    ft.Text("暂无消息", size=14, color=ft.Colors.GREY_400),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                padding=60, alignment=ft.alignment.center,
            ))
        self._list_view.controls = tiles
        try:
            self.page.update()
        except Exception:
            pass

    def _mark_read(self, mid):
        self._read_ids.add(mid)
        self._save_read_ids()
        self._render()

    def _mark_all_read(self):
        messages = self._get_messages()
        for m in messages:
            self._read_ids.add(m['id'])
        self._save_read_ids()
        self._render()
