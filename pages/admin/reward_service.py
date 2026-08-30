# pages/admin/reward_service.py
"""奖励发放服务：支持经验/物品/礼包，移植自桌面版 RewardManager"""
import datetime


class RewardService:
    def __init__(self, db):
        self.db = db  # TursoClient 或 LocalDB，需支持 execute/executemany/事务
        self._tables_ensured = False

    def _now(self):
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _ensure_tables(self):
        """确保经验历史表等存在（只执行一次）"""
        if self._tables_ensured:
            return
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS experience_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    exp_time TEXT DEFAULT (datetime('now','localtime')),
                    exp_amount INTEGER,
                    old_exp INTEGER,
                    new_exp INTEGER,
                    reason TEXT,
                    operator TEXT DEFAULT '管理员'
                )
            """)
            self._tables_ensured = True
        except Exception as e:
            print(f"[reward_svc] ensure tables fail: {e}")

    def user_exists(self, user_id):
        r = self.db.fetch_one("SELECT 1 FROM users WHERE user_id=?", [user_id])
        return r is not None

    # ================================================================
    # 通用发放入口
    # ================================================================
    def distribute(self, user_id, reward_type, value=0, item_id=None,
                   item_quantity=1, reason="管理员手动发放", operator="管理员"):
        """发放奖励，支持 experience/item（score/star/lottery 已从UI移除但代码保留）"""
        self._ensure_tables()
        if not self.user_exists(user_id):
            return False, f"用户ID {user_id} 不存在"

        # 负数校验
        if reward_type != 'item' and value is not None and int(value) < 0:
            return False, "数值不能为负数"
        if reward_type == 'item' and item_quantity is not None and int(item_quantity) < 0:
            return False, "数量不能为负数"

        handlers = {
            'score': self._award_score,
            'experience': self._award_experience,
            'star': self._award_star,
            'item': self._award_item,
            'lottery': self._award_lottery,
        }
        handler = handlers.get(reward_type)
        if not handler:
            return False, f"不支持的奖励类型: {reward_type}"

        try:
            if reward_type == 'item':
                if not item_id:
                    return False, "物品奖励需要指定物品ID"
                ok, msg = handler(user_id, item_id, item_quantity, reason, operator)
            else:
                ok, msg = handler(user_id, value, reason, operator)

            if ok:
                # 记录发放日志
                self.db.execute(
                    """INSERT INTO reward_distribution
                       (user_id, reward_type, reward_value, item_id, item_quantity, reason, operator, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [user_id, reward_type,
                     float(value if reward_type != 'item' else item_quantity),
                     item_id, item_quantity if reward_type == 'item' else None,
                     reason, operator, self._now()])
                # 用户消息通知（含变化前后值）
                type_names = {'score': '积分', 'experience': '经验', 'star': '星星', 'item': '物品', 'lottery': '抽奖次数'}
                tname = type_names.get(reward_type, reward_type)
                if reward_type == 'item':
                    item = self.db.fetch_one("SELECT name, quality FROM items WHERE id=?", [item_id])
                    iname = item['name'] if item else f'物品{item_id}'
                    iquality = item.get('quality','') if item else ''
                    qtag = f'[{iquality}]' if iquality else ''
                    ui = self.db.fetch_one("SELECT quantity FROM user_items WHERE user_id=? AND item_id=?", [user_id, item_id])
                    cur_qty = int(ui['quantity'] or 0) if ui else 0
                    detail = f"【奖励发放】{qtag}{iname}\n获得：×{item_quantity}\n当前持有：{cur_qty}\n原因：{reason}\n操作人：{operator}"
                    self.db.add_user_message(user_id, '奖励发放', detail, 'reward')
                elif reward_type == 'score':
                    u = self.db.fetch_one("SELECT score FROM users WHERE user_id=?", [user_id])
                    cur = int(u['score'] or 0) if u else 0
                    detail = f"【奖励发放】积分\n获得：+{value}\n变化：{cur - int(value)} → {cur}\n原因：{reason}\n操作人：{operator}"
                    self.db.add_user_message(user_id, '奖励发放', detail, 'reward')
                elif reward_type == 'experience':
                    u = self.db.fetch_one("SELECT experience FROM users WHERE user_id=?", [user_id])
                    cur = int(u['experience'] or 0) if u else 0
                    detail = f"【奖励发放】经验\n获得：+{value}\n变化：{cur - int(value)} → {cur}\n原因：{reason}\n操作人：{operator}"
                    self.db.add_user_message(user_id, '奖励发放', detail, 'reward')
                elif reward_type == 'star':
                    u = self.db.fetch_one("SELECT total_stars FROM users WHERE user_id=?", [user_id])
                    cur = int(u['total_stars'] or 0) if u else 0
                    detail = f"【奖励发放】星星\n获得：+{value}\n变化：{cur - int(value)} → {cur}\n原因：{reason}\n操作人：{operator}"
                    self.db.add_user_message(user_id, '奖励发放', detail, 'reward')
                else:
                    detail = f"【奖励发放】{tname} +{value}\n原因：{reason}\n操作人：{operator}"
                    self.db.add_user_message(user_id, '奖励发放', detail, 'reward')
            return ok, msg
        except Exception as e:
            return False, f"发放失败: {e}"

    # ================================================================
    # 各类型发放
    # ================================================================
    def _award_score(self, user_id, value, reason, operator="管理员"):
        u = self.db.fetch_one("SELECT score FROM users WHERE user_id=?", [user_id])
        old = int(u['score'] or 0) if u else 0
        new = old + int(value)
        self.db.execute("UPDATE users SET score=? WHERE user_id=?", [new, user_id])
        self.db.execute(
            """INSERT INTO score_record
               (user_id, score_time, score_type, score_name, score_amount, score_count,
                description, old_score, new_score, remark_edit)
               VALUES (?, ?, 7, 19, ?, 1, ?, ?, ?, '管理员发放')""",
            [user_id, self._now(), int(value), reason, old, new])
        return True, f"积分+{value} (当前{new})"

    def _award_experience(self, user_id, value, reason, operator="管理员"):
        u = self.db.fetch_one("SELECT experience, level_id FROM users WHERE user_id=?", [user_id])
        old = int(u['experience'] or 0) if u else 0
        new = old + int(value)
        self.db.execute("UPDATE users SET experience=? WHERE user_id=?", [new, user_id])
        # 检查升级（循环直到不够升）
        self._check_level_up(user_id, new)
        # 经验历史记录
        self.db.execute(
            """INSERT INTO experience_records
               (user_id, exp_time, exp_amount, old_exp, new_exp, reason, operator)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [user_id, self._now(), int(value), old, new, reason, operator])
        return True, f"经验+{value} (当前{new})"

    def _check_level_up(self, user_id, new_exp):
        """循环检查升级，直到经验不够升下一级"""
        try:
            u = self.db.fetch_one("SELECT level_id FROM users WHERE user_id=?", [user_id])
            cur = int(u['level_id'] or 1) if u else 1
            while cur < 200:
                req = self.db.fetch_one("SELECT required_experience FROM levels WHERE level_id=?", [cur])
                required = int(req['required_experience'] or 100) if req else 100
                if new_exp >= required:
                    cur += 1
                    self.db.execute("UPDATE users SET level_id=? WHERE user_id=?", [cur, user_id])
                    self.db.add_user_message(user_id, '等级提升',
                        f'【等级提升】恭喜升级到 Lv.{cur}\n当前经验：{new_exp}\n继续努力解锁更多功能！', 'levelup')
                else:
                    break
        except Exception:
            pass

    def _award_star(self, user_id, value, reason, operator="管理员"):
        u = self.db.fetch_one("SELECT total_stars FROM users WHERE user_id=?", [user_id])
        old = int(u['total_stars'] or 0) if u else 0
        new = old + int(value)
        self.db.execute("UPDATE users SET total_stars=? WHERE user_id=?", [new, user_id])
        self.db.execute(
            """INSERT INTO star_change_records (user_id, change_amount, change_type, description, change_time)
               VALUES (?, ?, 'admin', ?, ?)""",
            [user_id, int(value), reason, self._now()])
        return True, f"星星+{value} (当前{new})"

    def _award_item(self, user_id, item_id, quantity, reason, operator="管理员"):
        """原子累加：先UPDATE quantity=quantity+?，影响0行则INSERT"""
        qty = int(quantity)
        # 原子累加（避免并发竞态）
        result = self.db.execute(
            "UPDATE user_items SET quantity = quantity + ? WHERE user_id=? AND item_id=?",
            [qty, user_id, item_id])
        # 从Turso响应解析affected_row_count
        affected = 0
        try:
            affected = result["results"][0]["response"]["result"]["affected_row_count"]
        except Exception:
            pass
        if affected == 0:
            # 没有现有记录，INSERT（并发下可能唯一键冲突，冲突则再UPDATE）
            try:
                self.db.execute(
                    "INSERT INTO user_items (user_id, item_id, quantity) VALUES (?, ?, ?)",
                    [user_id, item_id, qty])
            except Exception:
                self.db.execute(
                    "UPDATE user_items SET quantity = quantity + ? WHERE user_id=? AND item_id=?",
                    [qty, user_id, item_id])
        # 操作历史
        self.db.execute(
            """INSERT INTO item_operation_history
               (user_id, operation_type, item_id, quantity, details, operation_time)
               VALUES (?, 'admin_grant', ?, ?, ?, ?)""",
            [user_id, item_id, qty, reason, self._now()])
        item = self.db.fetch_one("SELECT name FROM items WHERE id=?", [item_id])
        name = item['name'] if item else f"物品{item_id}"
        return True, f"{name}×{qty}"

    def _award_lottery(self, user_id, value, reason, operator="管理员"):
        existing = self.db.fetch_one("SELECT count FROM free_lottery_counts WHERE user_id=?", [user_id])
        now = self._now()
        if existing:
            new_cnt = int(existing['count'] or 0) + int(value)
            self.db.execute("UPDATE free_lottery_counts SET count=?, updated_at=? WHERE user_id=?",
                            [new_cnt, now, user_id])
        else:
            new_cnt = int(value)
            self.db.execute("INSERT INTO free_lottery_counts (user_id, count, created_at, updated_at) VALUES (?, ?, ?, ?)",
                            [user_id, int(value), now, now])
        return True, f"抽奖次数+{value} (当前{new_cnt})"

    # ================================================================
    # 礼包发放（批量添加礼包物品）
    # ================================================================
    def distribute_gift(self, user_id, gift_item_id, quantity=1,
                        reason="管理员发放礼包", operator="管理员"):
        """发放礼包：直接添加礼包物品到用户背包"""
        self._ensure_tables()
        if not self.user_exists(user_id):
            return False, f"用户ID {user_id} 不存在"
        if int(quantity) < 0:
            return False, "数量不能为负数"
        # 检查礼包是否有掉落配置
        cfg = self.db.fetch_one("SELECT COUNT(*) as c FROM gift_pack_rules WHERE gift_item_id=?", [gift_item_id])
        if not cfg or cfg['c'] == 0:
            return False, "该礼包没有配置掉落物品，无法发放"
        try:
            ok, msg = self._award_item(user_id, gift_item_id, quantity, reason, operator)
            if not ok:
                return False, msg
            self.db.execute(
                """INSERT INTO reward_distribution
                   (user_id, reward_type, reward_value, item_id, item_quantity, reason, operator, created_at)
                   VALUES (?, 'gift', ?, ?, ?, ?, ?, ?)""",
                [user_id, float(quantity), gift_item_id, quantity, reason, operator, self._now()])
            item = self.db.fetch_one("SELECT name FROM items WHERE id=?", [gift_item_id])
            name = item['name'] if item else f"礼包{gift_item_id}"
            gift_item = self.db.fetch_one("SELECT name, quality FROM items WHERE id=?", [gift_item_id])
            gquality = gift_item.get('quality','') if gift_item else ''
            qtag = f'[{gquality}]' if gquality else ''
            detail = f"【礼包发放】{qtag}{name} ×{quantity}\n原因：{reason}\n操作人：{operator}\n提示：请到背包中开启礼包获取掉落物品"
            self.db.add_user_message(user_id, '礼包发放', detail, 'gift')
            return True, f"成功发放 {name}×{quantity}"
        except Exception as e:
            return False, f"礼包发放失败: {e}"

    # ================================================================
    # 背包操作
    # ================================================================
    def update_backpack_item(self, user_id, item_id, new_quantity, operator="管理员"):
        """修改用户背包物品数量"""
        existing = self.db.fetch_one(
            "SELECT quantity FROM user_items WHERE user_id=? AND item_id=?", [user_id, item_id])
        if not existing:
            return False, "用户背包中没有该物品"
        old = int(existing['quantity'] or 0)
        self.db.execute("UPDATE user_items SET quantity=? WHERE user_id=? AND item_id=?",
                        [new_quantity, user_id, item_id])
        self.db.execute(
            """INSERT INTO item_operation_history
               (user_id, operation_type, item_id, quantity, details, operation_time)
               VALUES (?, 'admin_edit', ?, ?, '修改数量 %d→%d' % (old, new_quantity), ?)""",
            [user_id, item_id, new_quantity - old, self._now()])
        item = self.db.fetch_one("SELECT name FROM items WHERE id=?", [item_id])
        iname = item['name'] if item else f'物品{item_id}'
        item4 = self.db.fetch_one("SELECT name, quality FROM items WHERE id=?", [item_id])
        q4 = item4.get('quality','') if item4 else ''
        qtag4 = f'[{q4}]' if q4 else ''
        admin_name = getattr(self, 'page', None) and getattr(self.page, '_user_data', {}).get('username', '管理员') or '管理员'
        self.db.add_user_message(user_id, '背包变更',
            f'【背包变更】{qtag4}{iname}\n数量：{old} → {new_quantity}\n操作人：{admin_name}', 'backpack')
        return True, f"数量已更新为 {new_quantity}"

    def delete_backpack_item(self, user_id, item_id, operator="管理员"):
        """删除用户背包物品"""
        existing = self.db.fetch_one(
            "SELECT quantity FROM user_items WHERE user_id=? AND item_id=?", [user_id, item_id])
        if not existing:
            return False, "用户背包中没有该物品"
        self.db.execute("DELETE FROM user_items WHERE user_id=? AND item_id=?", [user_id, item_id])
        self.db.execute(
            """INSERT INTO item_operation_history
               (user_id, operation_type, item_id, quantity, details, operation_time)
               VALUES (?, 'admin_delete', ?, ?, '管理员删除', ?)""",
            [user_id, item_id, int(existing['quantity'] or 0), self._now()])
        item = self.db.fetch_one("SELECT name FROM items WHERE id=?", [item_id])
        iname = item['name'] if item else f'物品{item_id}'
        item5 = self.db.fetch_one("SELECT name, quality FROM items WHERE id=?", [item_id])
        q5 = item5.get('quality','') if item5 else ''
        qtag5 = f'[{q5}]' if q5 else ''
        admin_name = getattr(self, 'page', None) and getattr(self.page, '_user_data', {}).get('username', '管理员') or '管理员'
        self.db.add_user_message(user_id, '物品移除',
            f'【物品移除】{qtag5}{iname}\n原数量：{int(existing["quantity"] or 0)}\n操作人：{admin_name}', 'backpack')
        return True, "已从背包移除"
