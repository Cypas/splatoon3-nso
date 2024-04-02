import datetime
import re
from datetime import timedelta

time_format_ymdh = "%Y-%m-%dT%H"


# 类 时区工具
class TimeUtil(object):
    @classmethod
    def parse_timezone(cls, timezone):
        """
        解析时区表示
        :param timezone: str eg: +8
        :return: dict{symbol, offset}
        """
        result = re.match(r"(?P<symbol>[+-])(?P<offset>\d+)", timezone)
        symbol = result.groupdict()["symbol"]
        offset = int(result.groupdict()["offset"])

        return {"symbol": symbol, "offset": offset}

    @classmethod
    def convert_timezone(cls, dt, timezone="+0") -> datetime.datetime:
        """默认是utc时间，需要提供时区"""
        result = cls.parse_timezone(timezone)
        symbol = result["symbol"]

        offset = result["offset"]

        if symbol == "+":
            return dt + timedelta(hours=offset)
        elif symbol == "-":
            return dt - timedelta(hours=offset)
        else:
            raise Exception("dont parse timezone format")


def get_expire_time() -> str:
    """计算过期时间 字符串 精确度为 ymdh"""
    # 计算过期时间
    time_now = get_time_now_china()
    time_now_h = time_now.hour
    # 计算过期时间字符串
    # 判断当前小时是奇数还是偶数
    expire_time: datetime
    if (time_now_h % 2) == 0:
        # 偶数
        expire_time = time_now + datetime.timedelta(hours=2)
    else:
        expire_time = time_now + datetime.timedelta(hours=1)
    expire_time_str = expire_time.strftime(time_format_ymdh).strip()
    return expire_time_str


def time_converter(time_str) -> datetime:
    """世界时字符串转日期 时间转换 年-月-日 时:分:秒"""
    # convert time to UTC+8
    dt = datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ")
    dt += datetime.timedelta(hours=8)
    return dt


def time_converter_yd(time_str):
    """时间转换 月-日"""
    dt = time_converter(time_str)
    return datetime.datetime.strftime(dt, "%m.%d")


def time_converter_hm(time_str):
    """时间转换 时:分"""
    dt = time_converter(time_str)
    return datetime.datetime.strftime(dt, "%H:%M")


def time_converter_mdhm(time_str):
    """时间转换 月-日 时:分"""
    dt = time_converter(time_str)
    return datetime.datetime.strftime(dt, "%m-%d %H:%M")


def time_converter_weekday(time_str):
    """时间转换 周几，如周一"""
    dt = time_converter(time_str)
    weekday = dt.weekday()
    return weekday


def get_time_ymd():
    """获取年月日"""
    dt = get_time_now_china().strftime("%Y-%m-%d")
    return dt


def get_time_y() -> int:
    """获取年"""
    year = get_time_now_china().year
    return year


def get_time_now_china() -> datetime.datetime:
    """获取中国所在东八区时间"""
    # 获取utc时间，然后转东8区时间
    utc_now = datetime.datetime.utcnow()
    convert_now = TimeUtil.convert_timezone(utc_now, "+8")
    return convert_now


def get_time_now_china_str(now=None) -> str:
    """获取中国所在东八区时间字符串"""
    if not now:
        now = get_time_now_china()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    return now_str


def get_time_now_china_date(time_str: str) -> datetime.datetime:
    """将东八区时间字符串转换为date对象"""
    dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    return dt


def utc_str_to_china_str(time_str: str) -> str:
    """splatoon3的世界时字符串转国内时区字符串
    输入字符串形如  %Y-%m-%dT%H:%M:%SZ
    输出字符串形如  %Y-%m-%d %H:%M:%S
    """
    china_time = get_time_now_china_str(time_converter(time_str))
    return china_time


def convert_td(td: timedelta) -> str:
    """timedelta类型数据格式化为字符串"""
    # 通过 timedelta类型 取秒
    seconds = td.seconds
    # 时
    RemainingSec = seconds % (24 * 3600)
    hours = RemainingSec // 3600
    # 分
    RemainingSec = RemainingSec % 3600
    minutes = RemainingSec // 60
    # 秒
    seconds = RemainingSec % 60
    str_time = f"{minutes:02}m:{seconds:02}s"
    return str_time
