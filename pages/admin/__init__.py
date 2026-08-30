# pages/admin/__init__.py
import flet as ft
from pages.admin.users import UserManagementTab
from pages.admin.tasks import TaskManagementTab
from pages.admin.score_history import ScoreHistoryTab
from pages.admin.exchange import ExchangeManagementTab
from pages.admin.words_settings import WordsSettingsTab
from pages.admin.time_limits import TimeLimitsTab
from pages.admin.guoxue import GuoxueManagementTab
from pages.admin.guoxue_config import GuoxueConfigTab
from pages.admin.reward_rules import RewardRulesTab
from pages.admin.reward_distribution import RewardDistributionTab
from pages.admin.gift_config import GiftConfigTab
from pages.admin.item_management import ItemManagementTab
from pages.admin.reward_history import RewardHistoryTab
from pages.admin.operation_history import OperationHistoryTab
from pages.admin.admin_logs import AdminLogsTab
from pages.admin.backpack import BackpackTab
from pages.admin.card_settings import CardSettingsTab
from pages.admin.cihai_config import CihaiConfigTab
from pages.admin.cihai_material import CihaiMaterialTab
from pages.admin.message_admin import MessageAdminTab


class AdminPage:
    """管理员后台管理页面（Flet实现，移动端适配，模块化，标签懒加载）"""

    def __init__(self, page: ft.Page):
        self.page = page
        self.user_data = page._user_data if hasattr(page, '_user_data') else {}

        # 只实例化（轻量），不调用 build()，选中时才构建
        self._tab_classes = [
            ("用户管理", ft.Icons.PEOPLE, UserManagementTab),
            ("时间限制", ft.Icons.SCHEDULE, TimeLimitsTab),
            ("赋能卡设置", ft.Icons.CONFIRMATION_NUMBER, CardSettingsTab),
            ("消息公告", ft.Icons.CAMPAIGN, MessageAdminTab),
            ("单词设置", ft.Icons.BOOK, WordsSettingsTab),
            ("国学管理", ft.Icons.HOME, GuoxueManagementTab),
            ("国学配置", ft.Icons.SETTINGS_APPLICATIONS, GuoxueConfigTab),
            ("辞海配置", ft.Icons.MENU_BOOK, CihaiConfigTab),
            ("辞海题库", ft.Icons.LIBRARY_BOOKS, CihaiMaterialTab),
            ("任务管理", ft.Icons.ASSIGNMENT, TaskManagementTab),
            ("商品管理", ft.Icons.SHOPPING_BAG, ExchangeManagementTab),
            ("物品管理", ft.Icons.INVENTORY, ItemManagementTab),
            ("礼包配置", ft.Icons.CARD_GIFTCARD, GiftConfigTab),
            ("奖励规则", ft.Icons.STAR, RewardRulesTab),
            ("奖励发放", ft.Icons.ADD_TASK, RewardDistributionTab),
            ("积分历史", ft.Icons.HISTORY, ScoreHistoryTab),
            ("奖励历史", ft.Icons.HISTORY, RewardHistoryTab),
            ("操作历史", ft.Icons.ACCESS_TIME, OperationHistoryTab),
            ("背包管理", ft.Icons.SHOPPING_BAG, BackpackTab),
            ("管理日志", ft.Icons.ADMIN_PANEL_SETTINGS, AdminLogsTab),
        ]
        self._tab_instances = {}   # {index: tab_instance}
        self._tab_contents = {}    # {index: built_content}

        # 所有标签先用loading占位，第一个立即异步构建
        tab_list = []
        for i, (name, icon, cls) in enumerate(self._tab_classes):
            content = self._loading_widget(name)
            tab_list.append(ft.Tab(text=name, icon=icon, content=content))

        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=200,
            indicator_color=ft.Colors.BLUE_600,
            label_color=ft.Colors.BLUE_600,
            unselected_label_color=ft.Colors.GREY_500,
            label_text_style=ft.TextStyle(size=11, weight=ft.FontWeight.W_600),
            unselected_label_text_style=ft.TextStyle(size=10),
            tab_alignment=ft.TabAlignment.START,
            scrollable=True,
            tabs=tab_list,
            expand=True,
            on_change=self._on_tab_change,
        )
        # 第一个标签异步加载
        name0, icon0, cls0 = self._tab_classes[0]
        page.run_task(self._build_tab, 0, cls0, name0)

    def _loading_widget(self, name=""):
        return ft.Container(
            content=ft.Column([
                ft.ProgressRing(width=36, height=36, color=ft.Colors.BLUE_400),
                ft.Text(f"加载{name}..." if name else "加载中...", size=12, color=ft.Colors.GREY_500),
            ], alignment=ft.MainAxisAlignment.CENTER,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            expand=True, alignment=ft.alignment.center,
        )

    def _on_tab_change(self, e):
        idx = e.control.selected_index
        if idx in self._tab_contents:
            # 已加载过，直接用缓存内容
            self.tabs.tabs[idx].content = self._tab_contents[idx]
            self.page.update()
            return
        if idx not in self._tab_instances:
            name, icon, cls = self._tab_classes[idx]
            # 先显示加载动画
            self.tabs.tabs[idx].content = self._loading_widget(name)
            self.page.update()
            # 异步构建（等待数据加载完成才显示UI）
            self.page.run_task(self._build_tab, idx, cls, name)

    async def _build_tab(self, idx, cls, name):
        import asyncio
        inst = cls(self.page)
        self._tab_instances[idx] = inst
        # 1. 构建UI结构（空列表）
        content = inst.build()
        # 2. 加载数据（await完成后才显示，避免空白）
        try:
            await inst.load_data()
        except Exception as e:
            print(f"[admin] {name} load_data error: {e}")
        # 3. 统一注入刷新栏（标题 + 刷新按钮）
        refresh_bar = inst._refresh_header(name)
        wrapped = ft.Column([refresh_bar, content], expand=True, spacing=2)
        # 4. 数据就绪，替换loading为完整UI
        self._tab_contents[idx] = wrapped
        self.tabs.tabs[idx].content = wrapped
        self.page.update()

    def build(self):
        return ft.Container(
            content=self.tabs,
            expand=True,
            padding=ft.padding.only(top=8, left=10, right=10, bottom=4),
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=[ft.Colors.BLUE_50, ft.Colors.INDIGO_50,
                        ft.Colors.PURPLE_50, ft.Colors.PINK_50],
            ),
        )


__all__ = [
    'AdminPage',
    'UserManagementTab', 'TaskManagementTab', 'ScoreHistoryTab',
    'ExchangeManagementTab', 'WordsSettingsTab', 'TimeLimitsTab', 'GuoxueManagementTab',
    'RewardRulesTab', 'RewardDistributionTab', 'GiftConfigTab',
    'ItemManagementTab', 'RewardHistoryTab', 'OperationHistoryTab',
     'BackpackTab','AdminLogsTab','CihaiConfigTab',
]
