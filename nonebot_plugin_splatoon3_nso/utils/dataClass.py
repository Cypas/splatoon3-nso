import datetime
import re
from datetime import timedelta

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

