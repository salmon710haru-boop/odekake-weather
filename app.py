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


def load_settings():
    """保存済みの地域を読み込む。初回は東京を使う。"""
    if not SETTINGS_FILE.exists():
        return {"city": "東京"}

    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as file:
            settings = json.load(file)

        if settings.get("city") in LOCATIONS:
            return settings
    except (json.JSONDecodeError, OSError):
        pass

    return {"city": "東京"}


def save_settings(city):
    """選択された地域をJSONファイルへ保存する。"""
    with SETTINGS_FILE.open("w", encoding="utf-8") as file:
        json.dump({"city": city}, file, ensure_ascii=False, indent=2)


def weather_code_to_text(weather_code):
    """Open-Meteoの天気コードを表示用の日本語に変換する。"""
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


def create_outerwear_message(temperature):
    """気温から上着の目安を作る。"""
    if temperature <= 10:
        return "厚めの上着がおすすめです。"
    if temperature <= 15:
        return "上着があると安心です。"
    return "上着は基本的に不要そうです。"


def get_weather(location):
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
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError("天気情報を取得できませんでした。") from error

    current = data["current"]
    hourly = data["hourly"]

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

    max_rain_probability = max(hourly["precipitation_probability"])

    if max_rain_probability >= 30:
        umbrella_message = "傘を持っていくと安心です。"
        need_umbrella = True
    else:
        umbrella_message = "傘はなくても大丈夫そうです。"
        need_umbrella = False

    return {
        "current_temperature": current["temperature_2m"],
        "weather_text": weather_code_to_text(current["weather_code"]),
        "max_rain_probability": max_rain_probability,
        "umbrella_message": umbrella_message,
        "outerwear_message": create_outerwear_message(current["temperature_2m"]),
        "need_umbrella": need_umbrella,
        "hourly_forecasts": hourly_forecasts,
    }


@app.route("/", methods=["GET", "POST"])
def home():
    settings = load_settings()
    error_message = None
    weather = None

    if request.method == "POST":
        city = request.form.get("city", "")

        if city in LOCATIONS:
            save_settings(city)
            settings = {"city": city}
        else:
            error_message = "選択できない地域です。"

    selected_city = settings["city"]
    location = LOCATIONS[selected_city]

    try:
        weather = get_weather(location)
    except RuntimeError as error:
        error_message = str(error)

    return render_template(
        "index.html",
        locations=LOCATIONS,
        selected_city=selected_city,
        location_name=location["name"],
        weather=weather,
        error_message=error_message,
    )


if __name__ == "__main__":
    app.run(debug=True)