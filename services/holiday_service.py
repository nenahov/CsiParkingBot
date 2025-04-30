import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)
BASE_URL = "https://calendar.kuzyak.in/api/calendar/"  # 2025/05/02


class HolidayService:
    def __init__(self):
        pass

    async def get_day_info(self, day: date) -> (bool, str):
        try:
            response = requests.get(BASE_URL + day.strftime("%Y/%m/%d"))
            data = response.json()
            logger.debug(f"{data}")
            is_working_day = data.get("isWorkingDay", True)  # вернет None, если ключа нет
            holiday = data.get("holiday", "Рабочий день" if is_working_day else "Выходной")
            return is_working_day, holiday
        except:
            return True, "Тяжелый день"
