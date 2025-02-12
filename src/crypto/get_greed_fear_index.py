import requests
from datetime import datetime, timezone

FNG_ALL_API_URL = "https://api.alternative.me/fng/?limit=0&format=json"
FNG_TODAY_API_URL = "https://api.alternative.me/fng/?limit=1&format=json"


def get_data():
    response = requests.get(FNG_ALL_API_URL)
    data = response.json().get("data")
    for entry in data:
        entry["date"] = datetime.fromtimestamp(int(entry["timestamp"]), tz=timezone.utc).strftime('%Y-%m-%d')
        del entry["timestamp"]
        entry.pop("time_until_update", None)
    return data

def format_with_sign(number):
    return f"{'+' if number > 0 else ''}{number:.2f}%"

def get_emoji_for_grade(grade):
    if "fear" in grade.lower():
        return "🟢"
    elif "greed" in grade.lower():
        return "🔴"
    else:
        return "🟡"

def get_insight(today_grade):
    insights = {
        "Extreme Fear": "*Extreme Fear* in the market—investors are highly cautious, which could indicate a buying opportunity.",
        "Fear": "*Fear* is present—sentiment is bearish, and traders are hesitant.",
        "Neutral": "*Neutral* market sentiment—investors are undecided, leading to mixed signals.",
        "Greed": "*Greed* is driving the market—investors are optimistic, but caution is advised.",
        "Extreme Greed": "*Extreme Greed* in the market—prices may be overheating, increasing the risk of a correction."
    }

    return insights.get(today_grade) + "\n"

def get_greed_fear_index():
    data = get_data()
    today_data, yesterday_data, last_week_data, last_month_data = data[0], data[1], data[7], data[30]

    today_index = int(today_data['value'])
    today_grade = today_data['value_classification'].title()
    today_emoji = get_emoji_for_grade(today_grade)

    
    def calculate_change(previous_index):
        return format_with_sign(((today_index - previous_index) / previous_index) * 100)

    yesterday_index = int(yesterday_data['value'])
    yesterday_grade = yesterday_data['value_classification'].title()
    yesterday_change = calculate_change(yesterday_index)
    

    last_week_index = int(last_week_data['value'])
    last_week_grade = last_week_data['value_classification'].title()
    last_week_change = calculate_change(last_week_index)

    last_month_index = int(last_month_data['value']) if last_month_data else None
    last_month_grade = last_month_data['value_classification'].title()
    last_month_change = calculate_change(last_month_index)


    msg = f"{today_emoji} *Greed and Fear Index*\n"
    msg += "```\n"
    msg += f"{'Today':<20}{'Yesterday':<20}{'Last Week':<20}{'Last Month':<20}\n"
    msg += "-" * 71 + "\n"

    msg += f"{today_grade:<20}{yesterday_grade:<20}{last_week_grade:<20}{last_month_grade:<20}\n"
    msg += f"{f'{today_index} (1-100)':<20}{yesterday_change:<20}{last_week_change:<20}{last_month_change:<20}\n"
    msg += "```"

    msg += get_insight(today_grade)

    return msg
