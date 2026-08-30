# pages/admin/message_admin.py
import flet as ft
import asyncio
from .base import AdminBaseTab


class MessageAdminTab(AdminBaseTab):
    """消息公告发送模块：给指定用户或全部用户发送系统消息"""

    def __init__(self, page):
        super().__init__(page)
        self._user_dd = None
        self._title_tf = None
        self._content_tf = None
        self._list_view = None
        self._users = []

    def build(self):
        # 用户下拉
        self._user_dd = ft.Dropdown(
            label="接收用户",
            hint_text="选择接收消息的用户",
            border_radius=8,
            expand=True,
            options=[],
        )
        # 消息类型
        self._type_dd = ft.Dropdown(
            label="消息类型",
            border_radius=8,
            expand=True,
            options=[
                ft.dropdown.Option(key="announcement", text="系统公告"),
                ft.dropdown.Option(key="system", text="系统通知"),
                ft.dropdown.Option(key="reward", text="奖励通知"),
                ft.dropdown.Option(key="warning", text="警告提醒"),
                ft.dropdown.Option(key="activity", text="活动通知"),
            ],
            value="announcement",
        )
        # 标题
        self._title_tf = ft.TextField(
            label="消息标题",
            hint_text="例如：系统维护通知",
            border_radius=8,
            expand=True,
        )
        # 内容
        self._content_tf = ft.TextField(
            label="消息内容",
            hint_text="输入详细消息内容...",
            multiline=True,
            min_lines=3,
            max_lines=6,
            border_radius=8,
            expand=True,
        )
        # 发送按钮
        send_btn = ft.ElevatedButton(
            "发送消息",
            icon=ft.Icons.SEND,
            on_click=self._on_send,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_600,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.padding.symmetric(horizontal=20, vertical=10),
            ),
        )
        # 发送表单卡片
        form_card = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.CAMPAIGN, size=20, color=ft.Colors.BLUE_600),
                    ft.Text("发送公告消息", size=15, weight=ft.FontWeight.W_700,
                            color=ft.Colors.BLUE_800),
                ], spacing=6),
                self._user_dd,
                self._type_dd,
                self._title_tf,
                self._content_tf,
                ft.Row([send_btn], alignment=ft.MainAxisAlignment.END),
            ], spacing=8, tight=True),
            bgcolor=ft.Colors.BLUE_50,
            border_radius=10,
            padding=ft.padding.all(12),
        )
        # 历史列表
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([
            form_card,
            ft.Container(height=6),
            ft.Text("最近发送记录", size=12, weight=ft.FontWeight.W_600,
                    color=ft.Colors.GREY_600),
            self._list_view,
        ], spacing=4, expand=True)

    async def load_data(self):
        await self._reload()

    async def _reload(self):
        import asyncio
        await asyncio.sleep(0.05)
        # 加载用户列表
        def _query_users():
            return self.db.fetch_all(
                "SELECT user_id, username FROM users ORDER BY user_id")
        users = await asyncio.to_thread(_query_users)
        self._users = users or []
        self._user_dd.options = [
            ft.dropdown.Option(key="0", text="【全部用户】")
        ] + [
            ft.dropdown.Option(key=str(u['user_id']),
                               text=f"{u['user_id']}:{u.get('username','')}")
            for u in self._users
        ]
        # 加载最近发送记录
        def _query_msgs():
            return self.db.fetch_all(
                """SELECT m.*, u.username
                   FROM (SELECT * FROM user_messages
                         ORDER BY created_at DESC LIMIT 50) m
                   LEFT JOIN users u ON m.user_id=u.user_id
                   ORDER BY m.created_at DESC""")
        msgs = await asyncio.to_thread(_query_msgs)
        self._render_list(msgs or [])
        try:
            self._user_dd.update()
            self._list_view.update()
        except Exception:
            pass

    def _render_list(self, msgs):
        type_colors = {
            'announcement': ft.Colors.BLUE_600,
            'system': ft.Colors.GREY_600,
            'reward': ft.Colors.ORANGE_600,
            'warning': ft.Colors.RED_600,
            'activity': ft.Colors.GREEN_600,
            'reward': ft.Colors.ORANGE_600,
            'gift': ft.Colors.PURPLE_600,
            'levelup': ft.Colors.AMBER_600,
            'backpack': ft.Colors.TEAL_600,
            'timelimit': ft.Colors.INDIGO_600,
            'card': ft.Colors.PURPLE_600,
            'task': ft.Colors.CYAN_600,
        }
        type_names = {
            'announcement': '公告', 'system': '系统', 'reward': '奖励',
            'warning': '警告', 'activity': '活动', 'gift': '礼包',
            'levelup': '升级', 'backpack': '背包', 'timelimit': '时限',
            'card': '赋能卡', 'task': '任务',
        }
        tiles = []
        for m in msgs:
            uid = m.get('user_id', 0)
            uname = m.get('username', '') or (f"用户{uid}" if uid else "全部用户")
            title = m.get('title', '')
            content = m.get('content', '') or ''
            mtype = m.get('message_type', 'system')
            created = str(m.get('created_at', ''))[:19]
            tcolor = type_colors.get(mtype, ft.Colors.GREY_500)
            tname = type_names.get(mtype, mtype)
            # 内容预览（截断）
            preview = content.replace('\n', ' ')[:80]
            if len(content) > 80:
                preview += '...'
            tiles.append(ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(
                            content=ft.Text(tname, size=10, color=ft.Colors.WHITE,
                                            weight=ft.FontWeight.W_700),
                            bgcolor=tcolor,
                            border_radius=4,
                            padding=ft.padding.symmetric(horizontal=6, vertical=1),
                        ),
                        ft.Text(title, size=13, weight=ft.FontWeight.W_700,
                                color=ft.Colors.GREY_800, expand=True),
                        ft.Text(created, size=10, color=ft.Colors.GREY_500),
                    ], spacing=4),
                    ft.Text(f"接收：{uname}", size=11, color=ft.Colors.GREY_700),
                    ft.Text(preview, size=11, color=ft.Colors.GREY_600),
                ], spacing=2, tight=True),
                bgcolor=ft.Colors.GREY_50,
                border_radius=8,
                padding=ft.padding.all(8),
                margin=ft.margin.only(bottom=4),
            ))
        if not tiles:
            tiles.append(ft.Container(
                content=ft.Text("暂无发送记录", size=12, color=ft.Colors.GREY_400),
                padding=ft.padding.all(20),
                alignment=ft.alignment.center,
            ))
        self._list_view.controls = tiles

    def _on_send(self, e=None):
        uid_str = self._user_dd.value
        title = (self._title_tf.value or '').strip()
        content = (self._content_tf.value or '').strip()
        if not uid_str:
            self.snack("请选择接收用户")
            return
        if not title:
            self.snack("请输入消息标题")
            return
        if not content:
            self.snack("请输入消息内容")
            return
        target_uid = int(uid_str)
        msg_type = self._type_dd.value or 'announcement'

        async def _do_send():
            self._show_refresh_loading("发送中...")
            try:
                admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
                if target_uid == 0:
                    # 全部用户：逐个发送
                    users = self.db.fetch_all("SELECT user_id FROM users")
                    count = 0
                    for u in users or []:
                        self.db.add_user_message(u['user_id'], title, content, msg_type)
                        count += 1
                    self._log_operation("send_announcement", "user_messages",
                                        target_id="all", target_name=f"全部{count}人",
                                        details=f"[{msg_type}]{title}")
                    self.snack(f"已发送给全部 {count} 个用户")
                else:
                    self.db.add_user_message(target_uid, title, content, msg_type)
                    uname = ''
                    for u in self._users:
                        if u['user_id'] == target_uid:
                            uname = u.get('username', '')
                            break
                    self._log_operation("send_message", "user_messages",
                                        target_id=target_uid, target_name=uname,
                                        details=f"[{msg_type}]{title}")
                    self.snack(f"已发送给 {uname or target_uid}")
                # 清空输入
                self._title_tf.value = ''
                self._content_tf.value = ''
                try:
                    self._title_tf.update()
                    self._content_tf.update()
                except Exception:
                    pass
                await self._reload()
            except Exception as ex:
                self.snack(f"发送失败: {ex}")
            finally:
                self._hide_refresh_loading()

        self.page.run_task(_do_send)
