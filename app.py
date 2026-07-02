import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from flask import Flask, render_template, request

app = Flask(__name__)

SETTINGS_FILE = Path("settings.json")

LOCATIONS = {
    "東京": {"name": "東京都", "latitude": 35.6762, "longitude": 139.6503},
    "大阪": {"name": "大阪府", "latitude": 34.6937, "longitude": 135.5023},
    "札幌": {"name": "北海道札幌市", "latitude": 43.0618, "longitude": 141.3545},
    "福岡": {"name": "福岡県福岡市", "latitude": 33.5904, "longitude": 130.4017},
    "那覇": {"name": "沖縄県那覇市", "latitude": 26.2124, "longitude": 127.6809},
}

DAILY_CHECKLIST_ITEMS = [
    {
        "id": "wallet",
        "icon": "👛",
        "name": "財布",
        "description": "現金・カードを確認",
    },
    {
        "id": "smartphone",
        "icon": "📱",
        "name": "スマホ",
        "description": "充電残量を確認",
    },
    {
        "id": "keys",
        "icon": "🔑",
        "name": "鍵",
        "description": "自宅の鍵を確認",
    },
    {
        "id": "transport_card",
        "icon": "💳",
        "name": "交通系ICカード",
        "description": "定期券・残高を確認",
    },
    {
        "id": "mobile_battery",
        "icon": "🔋",
        "name": "モバイルバッテリー",
        "description": "長時間の外出なら安心",
    },
    {
        "id": "tissues",
        "icon": "🧻",
        "name": "ハンカチ・ティッシュ",
        "description": "必要に応じて準備",
    },
]

ALL_CHECKLIST_ITEM_IDS = {
    "umbrella",
    "outerwear",
    *(item["id"] for item in DAILY_CHECKLIST_ITEMS),
}


def load_settings():
    """保存済みの地域・出発時刻・チェック状態を読み込む。"""
    settings = {
        "city": "東京",
        "departure_hour": 8,
        "checked_items": [],
    }

    if not SETTINGS_FILE.exists():
        return settings

    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as file:
            saved_settings = json.load(file)

        if saved_settings.get("city") in LOCATIONS:
            settings["city"] = saved_settings["city"]

        departure_hour = saved_settings.get("departure_hour")
        if isinstance(departure_hour, int) and 0 <= departure_hour <= 23:
            settings["departure_hour"] = departure_hour

        checked_items = saved_settings.get("checked_items", [])
        if isinstance(checked_items, list):
            settings["checked_items"] = [
                item
                for item in checked_items
                if item in ALL_CHECKLIST_ITEM_IDS
            ]

    except (json.JSONDecodeError, OSError, AttributeError):
        pass

    return settings


def save_settings(city, departure_hour, checked_items):
    """地域・出発時刻・チェック状態をJSONへ保存する。"""
    settings = {
        "city": city,
        "departure_hour": departure_hour,
        "checked_items": checked_items,
    }

    with SETTINGS_FILE.open("w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=2)


def weather_code_to_text(weather_code):
    """Open-Meteoの天気コードを日本語に変換する。"""
    if weather_code == 0:
        return "晴れ"
    if weather_code in (1, 2, 3):
        return "晴れ時々くもり"
    if weather_code in (45, 48):
        return "霧"
    if weather_code in (51, 53, 55, 56, 57):
        return "霧雨"
    if weather_code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "雨"
    if weather_code in (71, 73, 75, 77, 85, 86):
        return "雪"
    if weather_code in (95, 96, 99):
        return "雷雨"

    return "不明"


def create_outerwear_recommendation(temperature):
    """出発時刻の気温から上着の必要性を判定する。"""
    if temperature <= 10:
        return True, "厚めの上着がおすすめです。"

    if temperature <= 15:
        return True, "上着があると安心です。"

    return False, "上着は基本的に不要そうです。"


def get_weather(location, departure_hour):
    """Open-Meteoから当日の天気情報を取得する。"""
    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": "temperature_2m,weather_code",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "timezone": "Asia/Tokyo",
        "forecast_days": 1,
    }

    url = "https://api.open-meteo.com/v1/forecast?" + urlencode(params)

    try:
        with urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        current = data["current"]
        hourly = data["hourly"]

    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ) as error:
        raise RuntimeError("天気情報を取得できませんでした。") from error

    hourly_forecasts = []

    for time, temperature, rain_probability in zip(
        hourly["time"],
        hourly["temperature_2m"],
        hourly["precipitation_probability"],
    ):
        hourly_forecasts.append(
            {
                "time": time[11:16],
                "temperature": temperature,
                "rain_probability": rain_probability,
            }
        )

    if not hourly_forecasts:
        raise RuntimeError("時間別の天気情報を取得できませんでした。")

    departure_time = f"{departure_hour:02d}:00"

    departure_forecast = next(
        (
            forecast
            for forecast in hourly_forecasts
            if forecast["time"] == departure_time
        ),
        hourly_forecasts[0],
    )

    departure_rain_probability = departure_forecast["rain_probability"]
    need_outerwear, outerwear_message = create_outerwear_recommendation(
        departure_forecast["temperature"]
    )

    if departure_rain_probability >= 30:
        need_umbrella = True
        umbrella_message = (
            f"{departure_forecast['time']}の降水確率は"
            f"{departure_rain_probability}%です。傘を持っていくと安心です。"
        )
    else:
        need_umbrella = False
        umbrella_message = (
            f"{departure_forecast['time']}の降水確率は"
            f"{departure_rain_probability}%です。傘はなくても大丈夫そうです。"
        )

    return {
        "current_temperature": current["temperature_2m"],
        "weather_text": weather_code_to_text(current["weather_code"]),
        "max_rain_probability": max(hourly["precipitation_probability"]),
        "departure_time": departure_forecast["time"],
        "departure_temperature": departure_forecast["temperature"],
        "departure_rain_probability": departure_rain_probability,
        "need_umbrella": need_umbrella,
        "umbrella_message": umbrella_message,
        "need_outerwear": need_outerwear,
        "outerwear_message": outerwear_message,
        "hourly_forecasts": hourly_forecasts,
    }


def build_checklist(weather):
    """天気に応じた持ち物と毎日の持ち物を作る。"""
    weather_items = []

    if weather["need_umbrella"]:
        weather_items.append(
            {
                "id": "umbrella",
                "icon": "☂",
                "name": "傘",
                "description": "出発時刻に雨の可能性あり",
            }
        )

    if weather["need_outerwear"]:
        weather_items.append(
            {
                "id": "outerwear",
                "icon": "🧥",
                "name": "上着",
                "description": "出発時刻の気温に合わせて準備",
            }
        )

    return {
        "weather_items": weather_items,
        "daily_items": DAILY_CHECKLIST_ITEMS,
        "all_items": weather_items + DAILY_CHECKLIST_ITEMS,
    }


@app.route("/", methods=["GET", "POST"])
def home():
    settings = load_settings()
    error_message = None

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "update_settings":
            city = request.form.get("city", "")
            departure_hour_text = request.form.get("departure_hour", "")

            try:
                departure_hour = int(departure_hour_text)
            except ValueError:
                departure_hour = -1

            if city not in LOCATIONS:
                error_message = "選択できない地域です。"

            elif not 0 <= departure_hour <= 23:
                error_message = "出発時刻は0時から23時の範囲で選択してください。"

            else:
                changed = (
                    city != settings["city"]
                    or departure_hour != settings["departure_hour"]
                )

                checked_items = [] if changed else settings["checked_items"]

                settings = {
                    "city": city,
                    "departure_hour": departure_hour,
                    "checked_items": checked_items,
                }

                save_settings(
                    settings["city"],
                    settings["departure_hour"],
                    settings["checked_items"],
                )

        elif action == "save_checklist":
            checked_items = request.form.getlist("checked_items")

            settings["checked_items"] = [
                item
                for item in checked_items
                if item in ALL_CHECKLIST_ITEM_IDS
            ]

            save_settings(
                settings["city"],
                settings["departure_hour"],
                settings["checked_items"],
            )

    selected_city = settings["city"]
    selected_departure_hour = settings["departure_hour"]
    location = LOCATIONS[selected_city]

    weather = None
    checklist = {
        "weather_items": [],
        "daily_items": [],
        "all_items": [],
    }

    try:
        weather = get_weather(location, selected_departure_hour)
        checklist = build_checklist(weather)

    except RuntimeError as error:
        error_message = str(error)

    checked_item_ids = set(settings["checked_items"])

    checked_count = sum(
        item["id"] in checked_item_ids
        for item in checklist["all_items"]
    )

    return render_template(
        "index.html",
        locations=LOCATIONS,
        selected_city=selected_city,
        selected_departure_hour=selected_departure_hour,
        departure_hours=range(24),
        location_name=location["name"],
        weather=weather,
        checklist=checklist,
        checked_item_ids=checked_item_ids,
        checked_count=checked_count,
        error_message=error_message,
    )


if __name__ == "__main__":
    app.run(debug=True)