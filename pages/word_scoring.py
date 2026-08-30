"""
单词掌握度评分算法（共享模块）
从 Pygame 版 _calculate_word_mastery 移植，供概览页和条形图页共用。
"""
import math
import datetime
import time

# 模块级缓存：{user_id: (timestamp, result)}，5分钟TTL
_SCORE_CACHE = {}
_CACHE_TTL = 300


def calc_length_score(word_len, base=0.5):
    """渐近对数长度因子：3字符=1.0，越长越趋近 base"""
    if word_len <= 3:
        return 1.0
    ratio = math.log(3) / math.log(word_len)
    return base + (1 - base) * ratio


def clear_score_cache(user_id=None):
    """清除评分缓存（切换用户时调用）"""
    if user_id is None:
        _SCORE_CACHE.clear()
    else:
        _SCORE_CACHE.pop(user_id, None)


def compute_all_scores(db, user_id):
    """
    批量计算用户所有单词的掌握度评分（带5分钟模块级缓存）。
    db: 提供 fetch_all 的数据库对象（LocalDB 或 TursoClient）
    返回 {word_id: (score, status)}
    """
    if user_id is None:
        return {}
    _cache_ts = time.time()
    cached = _SCORE_CACHE.get(user_id)
    if cached and _cache_ts - cached[0] < _CACHE_TTL:
        return cached[1]
    result = {}
    try:
        basic = db.fetch_all(
            "SELECT war.word_id, LENGTH(w.word) as word_len, "
            "COUNT(*) as total, "
            "SUM(CASE WHEN is_correct=1 THEN (1 - 0.3 * COALESCE(used_clue,0)) ELSE 0 END) as weighted, "
            "MAX(answer_time) as last_review "
            "FROM words_answer_records war "
            "JOIN words w ON war.word_id = w.word_id "
            "WHERE war.user_id = ? "
            "GROUP BY war.word_id",
            [user_id]
        )
        recent = db.fetch_all(
            "SELECT word_id, "
            "SUM(is_correct * (1 - 0.3 * COALESCE(used_clue,0))) as r_weighted, "
            "COUNT(*) as r_total "
            "FROM (SELECT word_id, is_correct, used_clue, "
            "ROW_NUMBER() OVER (PARTITION BY word_id ORDER BY answer_time DESC) as rn "
            "FROM words_answer_records WHERE user_id = ?) "
            "WHERE rn <= 100 GROUP BY word_id",
            [user_id]
        )
        recent_map = {r['word_id']: r for r in recent}
        now_dt = datetime.datetime.now()

        for b in basic:
            wid = b['word_id']
            total = int(b['total'] or 0)
            if total == 0:
                result[wid] = (0.0, 'unmastered')
                continue
            r = recent_map.get(wid, {})
            r_total = int(r.get('r_total') or 0)
            r_weighted = float(r.get('r_weighted') or 0)
            r_w = (r_weighted / r_total) if r_total > 0 else 0.0

            last_review = b.get('last_review')
            try:
                if isinstance(last_review, str):
                    lr = datetime.datetime.strptime(last_review, '%Y-%m-%d %H:%M:%S')
                else:
                    lr = last_review
                days_since = (now_dt - lr).days
            except Exception:
                days_since = 999
            time_score = max(0.3, 1.0 - 0.015 * days_since)
            length_score = calc_length_score(int(b['word_len'] or 1))

            score = 0.7 * r_w + 0.15 * length_score + 0.15 * time_score
            if total < 30:
                score = score * (total / 30.0)
            score = max(0.0, min(1.0, score))

            if score >= 0.80:
                status = 'mastered'
            elif score >= 0.6:
                status = 'learning'
            elif score >= 0.4:
                status = 'review'
            else:
                status = 'unmastered'
            result[wid] = (score, status)
    except Exception as e:
        print(f"[word_scoring] 评分计算失败: {e}")
    _SCORE_CACHE[user_id] = (_cache_ts, result)
    return result
