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
    "01": {"icon": "☀", "sun_alpha": 120},
    "02": {"icon": "⛅️", "sun_alpha": 110, "num_clouds": 3},
    "03": {"icon": "⛅️", "sun_alpha": 100, "num_clouds": 7},
    "04": {"icon": "🌥️", "sun_alpha": 80, "num_clouds": 10},
    "09": {"icon": "🌦️", "sun_alpha": 70, "rain_drop_count": 400, "num_clouds": 15},
    "10": {"icon": "🌧️", "rain_drop_count": 600, "num_clouds": 20},
    "11": {"icon": "⛈️", "rain_drop_count": 1000, "num_clouds": 30},
    "13": {"icon": "🌨️", "num_clouds": 5, "snow_count": 500},
    "50": {"icon": "🌫️", "num_clouds": 50}
}


class WeatherService:
    def __init__(self):
        pass

    async def get_weather_test(self, day: date) -> (str, dict, str):
        return "-25°", {"icon": "🌨️", "rain_drop_count": 600, "num_clouds": 20, "snow_count": 500}, "тест"

    async def get_weather_string(self, day: date) -> (str, dict, str):
        try:
            response = requests.get(BASE_URL, params=params)
            data = response.json()
            logger.debug(f"{data}")
            day_request = day.strftime("%Y-%m-%d")
            temp = ""
            weather = dict()
            desc = ""
            for forecast in data["list"]:
                date = forecast["dt_txt"].split()[0]
                if date == day_request:
                    time = forecast["dt_txt"].split()[1][:5]
                    if temp == "" or time == "12:00":
                        temp = f"{int(forecast["main"]["temp"]):+3d}°"
                        icon = forecast["weather"][0]["icon"][:2]
                        weather = weather_map.get(icon, dict())
                        desc = forecast["weather"][0]["description"]
                    if time == "12:00":
                        return temp, weather, desc
            return temp, weather, desc
        except:
            return "", dict(), ""

    async def get_weather_content(self, day: date):
        is_ok = False
        content = Bold(f"Погода на {day.strftime('%a %d.%m.%Y')}:")
        try:
            response = requests.get(BASE_URL, params=params)
            data = response.json()
            logger.debug(f"{data}")
            day_request = day.strftime("%Y-%m-%d")

            for forecast in data["list"]:
                date = forecast["dt_txt"].split()[0]
                if date == day_request:
                    is_ok = True
                    time = forecast["dt_txt"].split()[1][:5]
                    temp = f"{int(forecast["main"]["temp"]):+3d}"
                    desc = forecast["weather"][0]["description"]
                    icon = forecast["weather"][0]["icon"][:2]
                    content += Code(f"\n{time} {temp}°C {weather_map.get(icon, dict()).get("icon", '')} {desc}")
        except:
            pass
        if not is_ok:
            content += Italic("\nСервис погоды временно недоступен 🤷")
        return content

    async def get_weekly_weather_content(self):
        is_ok = False
        content = Bold("Погода на неделю:\n\n")
        try:
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

            # Обрабатываем дни в хронологическом порядке
            for day_str in sorted(forecast_by_date.keys()):
                # Преобразование строки в объект date для форматирования заголовка
                current_day = date.fromisoformat(day_str)
                day_header = Bold(f"Погода на {current_day.strftime('%a %d.%m.%Y')}:")
                day_content = day_header

                for forecast in forecast_by_date[day_str]:
                    time_str = forecast["dt_txt"].split()[1][:5]
                    temp = f"{int(forecast["main"]["temp"]):+3d}"
                    desc = forecast["weather"][0]["description"]
                    icon = forecast["weather"][0]["icon"][:2]
                    day_content += Code(f"\n{time_str} {temp}°C {weather_map.get(icon, dict()).get("icon", '')} {desc}")
                    is_ok = True

                content += day_content + "\n\n"
        except:
            pass

        # Если сервис не вернул прогнозы - уведомляем пользователя
        if not is_ok:
            content = Italic("Сервис погоды временно недоступен 🤷")
        return content
