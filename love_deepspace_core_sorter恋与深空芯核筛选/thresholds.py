"""
阈值表：所有词条在强化次数 0~7 下的最小值、平均值、最大值。
百分比数值按数字存储（如 8.5% 存储为 8.5）。
"""

# === 阈值表 ===

THRESHOLDS = {
    "加成": {
        0: {"min": 7.0, "avg": 8.5, "max": 10.0},
        1: {"min": 10.5, "avg": 12.8, "max": 15.0},
        2: {"min": 14.0, "avg": 17.0, "max": 20.0},
        3: {"min": 17.5, "avg": 21.3, "max": 25.0},
        4: {"min": 21.0, "avg": 25.5, "max": 30.0},
        5: {"min": 24.5, "avg": 29.8, "max": 35.0},
        6: {"min": 28.0, "avg": 34.0, "max": 40.0},
        7: {"min": 31.5, "avg": 38.3, "max": 45.0},
    },
    "暴击": {
        0: {"min": 1.1, "avg": 1.4, "max": 1.6},
        1: {"min": 1.7, "avg": 2.1, "max": 2.4},
        2: {"min": 2.3, "avg": 2.8, "max": 3.2},
        3: {"min": 2.9, "avg": 3.5, "max": 4.0},
        4: {"min": 3.5, "avg": 4.2, "max": 4.8},
        5: {"min": 4.1, "avg": 4.9, "max": 5.6},
        6: {"min": 4.7, "avg": 5.6, "max": 6.4},
        7: {"min": 5.3, "avg": 6.3, "max": 7.2},
    },
    "爆伤": {
        0: {"min": 2.2, "avg": 2.7, "max": 3.2},
        1: {"min": 3.4, "avg": 4.1, "max": 4.8},
        2: {"min": 4.6, "avg": 5.5, "max": 6.4},
        3: {"min": 5.8, "avg": 6.9, "max": 8.0},
        4: {"min": 7.0, "avg": 8.3, "max": 9.6},
        5: {"min": 8.2, "avg": 9.7, "max": 11.2},
        6: {"min": 9.4, "avg": 11.1, "max": 12.8},
        7: {"min": 10.6, "avg": 12.5, "max": 14.4},
    },
    "攻击": {
        0: {"min": 42, "avg": 51, "max": 60},
        1: {"min": 64, "avg": 77, "max": 90},
        2: {"min": 86, "avg": 103, "max": 120},
        3: {"min": 108, "avg": 129, "max": 150},
        4: {"min": 130, "avg": 155, "max": 180},
        5: {"min": 152, "avg": 181, "max": 210},
        6: {"min": 174, "avg": 207, "max": 240},
        7: {"min": 196, "avg": 233, "max": 270},
    },
    "防御": {
        0: {"min": 21, "avg": 26, "max": 30},
        1: {"min": 32, "avg": 39, "max": 45},
        2: {"min": 43, "avg": 52, "max": 60},
        3: {"min": 54, "avg": 65, "max": 75},
        4: {"min": 65, "avg": 78, "max": 90},
        5: {"min": 76, "avg": 91, "max": 105},
        6: {"min": 87, "avg": 104, "max": 120},
        7: {"min": 98, "avg": 117, "max": 135},
    },
    "生命": {
        0: {"min": 800, "avg": 1000, "max": 1200},
        1: {"min": 1200, "avg": 1500, "max": 1800},
        2: {"min": 1600, "avg": 2000, "max": 2400},
        3: {"min": 2000, "avg": 2500, "max": 3000},
        4: {"min": 2400, "avg": 3000, "max": 3600},
        5: {"min": 2800, "avg": 3500, "max": 4200},
        6: {"min": 3200, "avg": 4000, "max": 4800},
        7: {"min": 3600, "avg": 4500, "max": 5400},
    },
    "虚弱": {
        0: {"min": 1.8, "avg": 2.2, "max": 2.6},
        1: {"min": 2.7, "avg": 3.3, "max": 3.8},
        2: {"min": 3.6, "avg": 4.3, "max": 5.0},
        3: {"min": 4.5, "avg": 5.4, "max": 6.2},
        4: {"min": 5.4, "avg": 6.4, "max": 7.4},
        5: {"min": 6.3, "avg": 7.5, "max": 8.6},
        6: {"min": 7.2, "avg": 8.5, "max": 9.8},
        7: {"min": 8.1, "avg": 9.6, "max": 11.0},
    },
    "誓约": {
        0: {"min": 0.8, "avg": 1.1, "max": 1.4},
        1: {"min": 1.2, "avg": 1.6, "max": 2.0},
        2: {"min": 1.6, "avg": 2.1, "max": 2.6},
        3: {"min": 2.0, "avg": 2.6, "max": 3.2},
        4: {"min": 2.4, "avg": 3.1, "max": 3.8},
        5: {"min": 2.8, "avg": 3.6, "max": 4.4},
        6: {"min": 3.2, "avg": 4.1, "max": 5.0},
        7: {"min": 3.6, "avg": 4.6, "max": 5.6},
    },
}

# === 别名映射：OCR 可能识别出的变体 → 标准名称 ===

ALIAS_MAP = {
    # 暴击
    "暴击率": "暴击",
    "暴击": "暴击",
    # 爆伤
    "暴击伤害": "爆伤",
    "爆伤": "爆伤",
    "暴伤": "爆伤",
    # 加成类（攻击/防御/生命加成共用阈值表）
    "攻击加成": "加成",
    "防御加成": "加成",
    "生命加成": "加成",
    "加成": "加成",
    # 攻击
    "攻击力": "攻击",
    "攻击": "攻击",
    # 防御
    "防御力": "防御",
    "防御": "防御",
    # 生命
    "生命力": "生命",
    "生命": "生命",
    "生命值": "生命",
    "HP": "生命",
    # 虚弱增伤
    "虚弱增伤": "虚弱",
    "虚弱": "虚弱",
    # 誓约增伤
    "誓约增伤": "誓约",
    "誓约": "誓约",
}

# === 所有标准词条名列表 ===

STAT_NAMES = list(THRESHOLDS.keys())

# === 等级取值范围 ===

VALID_LEVELS = {0, 3, 6, 9, 12, 15}


def normalize_stat_name(raw: str) -> str | None:
    """将 OCR 识别出的原始词条名映射到标准名称，无法匹配返回 None。"""
    cleaned = raw.strip().rstrip("%").rstrip("+").strip()
    return ALIAS_MAP.get(cleaned, None)


def get_candidate_times(stat_name: str, value: float) -> list[int]:
    """返回该词条数值可能对应的强化次数列表（自动归一化词条名）。"""
    name = normalize_stat_name(stat_name) or stat_name
    if name not in THRESHOLDS:
        return []
    candidates = []
    for t in range(8):
        rng = THRESHOLDS[name][t]
        if rng["min"] <= value <= rng["max"]:
            candidates.append(t)
    return candidates


def get_threshold(stat_name: str, times: int) -> dict:
    """返回词条在指定强化次数下的 {min, avg, max} 阈值（自动归一化词条名）。"""
    name = normalize_stat_name(stat_name) or stat_name
    return THRESHOLDS[name][times]
