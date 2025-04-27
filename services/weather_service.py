import logging
import os
from datetime import date

import requests
from aiogram.utils.formatting import Bold, Italic, Code

logger = logging.getLogger(__name__)

API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
CITY = "Saint Petersburg,RU"
BASE_URL = "http://api.openweathermap.org/data/2.5/forecast"
params = {
    "q": CITY,
    "appid": API_KEY,
    "units": "metric",
    "lang": "ru"
}
weather_map = {
    "01": "☀",
    "02": "⛅️",
    "03": "⛅️",
    "04": "🌥️",
    "09": "🌦️",
    "10": "🌧️",
    "11": "⛈️",
    "13": "🌨️",
    "50": "🌫️"
}


class WeatherService:
    def __init__(self):
        pass

    async def get_weather_string(self, day: date) -> (str, str):
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        logger.debug(f"{data}")
        day_request = day.strftime("%Y-%m-%d")
        result = ""
        desc = ""
        for forecast in data["list"]:
            date = forecast["dt_txt"].split()[0]
            if date == day_request:
                time = forecast["dt_txt"].split()[1][:5]
                temp = str(int(forecast["main"]["temp"]))
                icon = forecast["weather"][0]["icon"][:2]
                if result == "" or time == "12:00":
                    result = f"{temp}{weather_map.get(icon, '')}"
                    desc = forecast["weather"][0]["description"]
                if time == "12:00":
                    return result, desc
        return result, desc

    async def get_weather_content(self, day: date):
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        logger.debug(f"{data}")
        day_request = day.strftime("%Y-%m-%d")

        is_ok = False
        content = Bold(f"Погода на {day.strftime('%a %d.%m.%Y')}:")
        for forecast in data["list"]:
            date = forecast["dt_txt"].split()[0]
            if date == day_request:
                is_ok = True
                time = forecast["dt_txt"].split()[1][:5]
                temp = str(int(forecast["main"]["temp"])).rjust(3, " ")
                desc = forecast["weather"][0]["description"]
                icon = forecast["weather"][0]["icon"][:2]
                content += Code(f"\n{time} {temp}°C {weather_map.get(icon, "")} {desc}")
        if not is_ok:
            content += Italic("\nСервис временно недоступен 🤷")
        return content

    async def get_weekly_weather_content(self):
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        logger.debug(f"Weekly data: {data}")

        # Группируем прогнозы по датам
        forecast_by_date = {}
        for forecast in data["list"]:
            day_str = forecast["dt_txt"].split()[0]
            if day_str not in forecast_by_date:
                forecast_by_date[day_str] = []
            forecast_by_date[day_str].append(forecast)

        is_ok = False
        content = Bold("Погода на неделю:\n\n")
        # Обрабатываем дни в хронологическом порядке
        for day_str in sorted(forecast_by_date.keys()):
            # Преобразование строки в объект date для форматирования заголовка
            current_day = date.fromisoformat(day_str)
            day_header = Bold(f"Погода на {current_day.strftime('%a %d.%m.%Y')}:")
            day_content = day_header

            for forecast in forecast_by_date[day_str]:
                time_str = forecast["dt_txt"].split()[1][:5]
                temp = str(int(forecast["main"]["temp"])).rjust(3, " ")
                desc = forecast["weather"][0]["description"]
                icon = forecast["weather"][0]["icon"][:2]
                day_content += Code(f"\n{time_str} {temp}°C {weather_map.get(icon, '')} {desc}")
                is_ok = True

            content += day_content + "\n\n"

        # Если сервис не вернул прогнозы - уведомляем пользователя
        if not is_ok:
            content = Italic("Сервис временно недоступен 🤷")
        return content
