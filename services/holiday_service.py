import logging
from datetime import date

import requests
from bs4 import BeautifulSoup

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

    async def get_holidays(self, day: date):
        try:
            response = requests.get("https://www.calend.ru")
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Ищем блок с праздниками для указанной даты
            holidays_block = soup.find('div', id=f'div_{day.year}-{day.month}-{day.day}')

            if not holidays_block:
                return []

            # Извлекаем все названия праздников
            holidays = []
            for p_tag in holidays_block.find_all('p'):
                a_tag = p_tag.find('a', href=True)
                if a_tag and '/holidays/' in a_tag['href']:
                    holiday_name = a_tag.get_text(strip=True)
                    if holiday_name and not holiday_name.startswith("Все праздники") and holiday_name not in holidays:
                        holidays.append(holiday_name)

            return holidays

        except Exception as e:
            logger.error(f"Произошла ошибка: {e}")
            return []
