from __future__ import annotations

DEFAULT_RESEARCH_POOL: list[dict[str, str]] = [
    {"symbol": "sh600519", "code": "600519", "name": "贵州茅台", "sector": "白酒"},
    {"symbol": "sz000858", "code": "000858", "name": "五粮液", "sector": "白酒"},
    {"symbol": "sz300750", "code": "300750", "name": "宁德时代", "sector": "锂电池"},
    {"symbol": "sz002594", "code": "002594", "name": "比亚迪", "sector": "新能源汽车"},
    {"symbol": "sh601012", "code": "601012", "name": "隆基绿能", "sector": "光伏"},
    {"symbol": "sz300274", "code": "300274", "name": "阳光电源", "sector": "光伏"},
    {"symbol": "sh600036", "code": "600036", "name": "招商银行", "sector": "银行"},
    {"symbol": "sh601398", "code": "601398", "name": "工商银行", "sector": "银行"},
    {"symbol": "sz000333", "code": "000333", "name": "美的集团", "sector": "家电"},
    {"symbol": "sh600690", "code": "600690", "name": "海尔智家", "sector": "家电"},
    {"symbol": "sh601318", "code": "601318", "name": "中国平安", "sector": "保险"},
    {"symbol": "sh600030", "code": "600030", "name": "中信证券", "sector": "券商"},
    {"symbol": "sh601688", "code": "601688", "name": "华泰证券", "sector": "券商"},
    {"symbol": "sh600276", "code": "600276", "name": "恒瑞医药", "sector": "创新药"},
    {"symbol": "sz300760", "code": "300760", "name": "迈瑞医疗", "sector": "医疗器械"},
    {"symbol": "sh688981", "code": "688981", "name": "中芯国际", "sector": "半导体"},
    {"symbol": "sz002371", "code": "002371", "name": "北方华创", "sector": "半导体"},
    {"symbol": "sz300308", "code": "300308", "name": "中际旭创", "sector": "算力硬件"},
    {"symbol": "sz300502", "code": "300502", "name": "新易盛", "sector": "算力硬件"},
    {"symbol": "sh603259", "code": "603259", "name": "药明康德", "sector": "CXO"},
    {"symbol": "sh600809", "code": "600809", "name": "山西汾酒", "sector": "白酒"},
    {"symbol": "sh600941", "code": "600941", "name": "中国移动", "sector": "运营商"},
    {"symbol": "sh601899", "code": "601899", "name": "紫金矿业", "sector": "有色金属"},
    {"symbol": "sz002475", "code": "002475", "name": "立讯精密", "sector": "消费电子"},
]

MAX_RESEARCH_CANDIDATES = 36
DEFAULT_RECOMMENDATION_COUNT = 10
MIN_RECOMMENDATION_COUNT = 5
MAX_RECOMMENDATIONS_PER_SECTOR = 3
HISTORY_BAR_LIMIT = 60
