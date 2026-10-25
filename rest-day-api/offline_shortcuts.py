# -*- coding: utf-8 -*-
"""
中国大陆工作日离线判断（iOS Pythonista / 快捷指令）
来源：国务院办公厅《关于2026年部分节假日安排的通知》
国办发明电〔2025〕7号
默认读取北京时间当日。可选参数：YYYY-MM-DD（方便测试）。
工作日（含周末调休上班）返回 1；其余或未知年份返回空白。
不联网，不写入系统数据，未录入新年度安排时安全停用。
"""
from datetime import datetime, date, timezone, timedelta
import sys

TZ_CHINA = timezone(timedelta(hours=8))

HOLIDAYS = {
    2026: [
        ("2026-01-01", "2026-01-03"),
        ("2026-02-15", "2026-02-23"),
        ("2026-04-04", "2026-04-06"),
        ("2026-05-01", "2026-05-05"),
        ("2026-06-19", "2026-06-21"),
        ("2026-09-25", "2026-09-27"),
        ("2026-10-01", "2026-10-07"),
    ],
}

MAKEUP_WORKDAYS = {
    2026: {
        "2026-01-04", "2026-02-14", "2026-02-28",
        "2026-05-09", "2026-09-20", "2026-10-10",
    },
}

def is_workday(day):
    """返回 True/False；未知年份返回 None，避免误判执行。"""
    if day.year not in HOLIDAYS or day.year not in MAKEUP_WORKDAYS:
        return None
    d = day.isoformat()
    if d in MAKEUP_WORKDAYS[day.year]:
        return True
    for start, end in HOLIDAYS[day.year]:
        if start <= d <= end:
            return False
    return day.weekday() < 5

def main():
    target = datetime.now(TZ_CHINA).date()
    # Pythonista 快捷指令「参数」可以填写 YYYY-MM-DD 来调试
    for arg in sys.argv[1:]:
        if len(arg) == 10 and arg[4:5] == "-" and arg[7:8] == "-":
            try:
                target = date.fromisoformat(arg)
                break
            except ValueError:
                pass
    if is_workday(target) is True:
        sys.stdout.write("1")
    # 休息日或未配置年度故意不打印任何内容

if __name__ == "__main__":
    main()
