import re
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests

URL = "https://bitinfocharts.com/bitcoin-distribution-history.html"

RAW_RANGES = [
    "0 - 0.1 BTC",
    "0.1 - 1 BTC",
    "1 - 10 BTC",
    "10 - 100 BTC",
    "100 - 1,000 BTC",
    "1,000 - 10,000 BTC",
    "10,000 - 100,000 BTC",
    "100,000 - 1,000,000 BTC"
]

NEW_RANGES = {
    "0.001 - 1 BTC": ["0 - 0.1 BTC", "0.1 - 1 BTC"],
    "1 - 10 BTC": ["1 - 10 BTC"],
    "10 - 100 BTC": ["10 - 100 BTC"],
    "100+ BTC": ["100 - 1,000 BTC", "1,000 - 10,000 BTC", "10,000 - 100,000 BTC", "100,000 - 1,000,000 BTC"]
}


def get_data(start_date=None, end_date=None):
    response = requests.get(URL)
    if response.status_code != 200:
        exit()

    soup = BeautifulSoup(response.content, 'html.parser')
    script = soup.find('script', string=re.compile(r'new Dygraph')).string
    data_string = re.search(r'\[\[new Date\(".*?"\),.*?\]\]', script, re.DOTALL).group(0)
    data = eval(data_string.replace('new Date', '').replace('(', '').replace(')', ''))
    
    # Extract dates and values
    dates = [row[0].replace('"', '') for row in data]
    values = [row[1:] for row in data]

    # Convert to DataFrame
    formatted_data = []
    for date, value_row in zip(dates, values):
        new_data = {new_range: sum(value_row[RAW_RANGES.index(old_range)] for old_range in old_ranges if old_range in RAW_RANGES)
                    for new_range, old_ranges in NEW_RANGES.items()}
        new_data["Date"] = date
        formatted_data.append(new_data)

    df = pd.DataFrame(formatted_data)
    df["Date"] = pd.to_datetime(df["Date"], format='%Y/%m/%d')
    df = df.sort_values("Date").reset_index(drop=True)

    if start_date is None:
        start_date = df["Date"].min()
    else:
        start_date = pd.to_datetime(start_date)

    if end_date is None:
        end_date = datetime.now()
    else:
        end_date = pd.to_datetime(end_date)

    mask = (df["Date"] >= start_date) & (df["Date"] <= end_date)
    df = df[mask].reset_index(drop=True)
    df.set_index("Date", inplace=True)

    return df


def get_reversal(df):
    df = df.diff().iloc[1:]
    buying_reversals = {}
    selling_reversals = {}

    for category in NEW_RANGES.keys():
        category_data = df[category]

        yesterday_change = category_data.iloc[-2]
        day_before_yesterday_change = category_data.iloc[-3]

        yesterday_direction = "buying" if yesterday_change > 0 else "selling"
        day_before_yesterday_direction = "buying" if day_before_yesterday_change > 0 else "selling"

        if yesterday_direction != day_before_yesterday_direction:
            streak_count = 1
            for change in category_data.iloc[:-3].iloc[::-1]:
                direction = "buying" if change > 0 else "selling" if change < 0 else None
                if direction == day_before_yesterday_direction:
                    streak_count += 1
                else:
                    break

            if yesterday_direction == "buying":
                buying_reversals[category] = streak_count
            else:
                selling_reversals[category] = streak_count

    max_buying_streak = max(buying_reversals.values())
    max_selling_streak = max(selling_reversals.values())

    longest_buying_categories = [k for k, v in buying_reversals.items() if v == max_buying_streak]
    longest_selling_categories = [k for k, v in selling_reversals.items() if v == max_selling_streak]

    messages = []
    if max_buying_streak > 1:
        messages.append(
            f"{', '.join(longest_buying_categories)} shifted to buying *after {max_buying_streak} days of selling*."
        )
    if max_selling_streak > 1:
        messages.append(
            f"{', '.join(longest_selling_categories)} shifted to selling *after {max_selling_streak} days of buying*."
        )

    return "\n".join(messages) if messages else "No reversals detected."


def get_streaks(df):
    msg = ""
    df = df.diff().iloc[1:]

    streaks = {}
    for category in NEW_RANGES.keys():
        category_data = df[category]
        direction = None
        streak_count = 0

        for change in category_data.iloc[:-1].iloc[::-1]:
            if change > 0:
                if direction == "buying" or direction is None:
                    direction = "buying"

                    streak_count += 1
                else:
                    break
            elif change < 0:
                if direction == "selling" or direction is None:
                    direction = "selling"
                    streak_count += 1
                else:
                    break
            else:
                break

        streaks[category] = (direction, streak_count)

    max_streak_count = max(streak[1] for streak in streaks.values())

    max_streak_categories = [
        f"{category} {streak[0]}"
        for category, streak in streaks.items()
        if streak[1] == max_streak_count
    ]

    if max_streak_count > 1:
        categories_str = ", ".join(max_streak_categories)
        msg = f"{categories_str} for *{max_streak_count} days straight*."

    return msg if msg else "No streaks found."


def get_sudden_change(df, window_size=30, std_multiplier=1):
    df = df.diff().iloc[1:]
    yesterday = df.iloc[-2] #DEMO should be -2
    df = df.iloc[-(window_size + 2):-2]
    messages = []
    for category in NEW_RANGES.keys():
        # Calculate rolling stats for buying
        category_data = df[category]
        buying_data = category_data[category_data > 0]
        selling_data = abs(category_data[category_data < 0])  # Absolute value for selling

        # Rolling mean and std for buying
        buying_mean = buying_data.mean()
        buying_std = buying_data.std()
        buying_threshold = buying_mean + (std_multiplier * buying_std)

        # Rolling mean and std for selling
        selling_mean = selling_data.mean()
        selling_std = selling_data.std()
        selling_threshold = selling_mean + (std_multiplier * selling_std)

        # Check yesterday's value against thresholds
        value_yesterday = yesterday[category]
        if value_yesterday > 0 and value_yesterday > buying_threshold:
            messages.append(f"{category} increased their holdings by *{value_yesterday:.0f} BTC*, well above their monthly average of {buying_mean:.0f} BTC.")
        elif value_yesterday < 0 and abs(value_yesterday) > selling_threshold:
            messages.append(f"{category} decreased their holdings by *{abs(value_yesterday):.0f} BTC*, well above their monthly average of {selling_mean:.0f} BTC.")

    return "\n".join(messages) if messages else "No sudden increase/decrease in holdings detected."


def get_insight(df):
    insights = get_streaks(df)
    insights += "\n" + get_reversal(df)
    insights += "\n" +  get_sudden_change(df)

    insight_list = insights.split("\n")
    msg = "\n".join(f"*{i + 1})* {line}" for i, line in enumerate(insight_list) if line.strip())
    msg += "\n"
    return msg


def generate_message(data):
    today = data.iloc[-1]  # Most recent date
    yesterday = data.iloc[-2]  # One day before
    day_before_yesterday = data.iloc[-3]  # Two days before
    last_month = data.iloc[-31]  # 30 days ago

    # Calculate changes
    today_changes = today - yesterday
    yesterday_changes = yesterday - day_before_yesterday
    last_30_days_changes = today - last_month

    # Format data into a DataFrame
    df = pd.DataFrame({
        "BTC Addresses": data.columns,
        "# BTC Held Today": today.values,
        "Today": today_changes.values,
        "Yesterday": yesterday_changes.values,
        "Last Month": last_30_days_changes.values,
    })

    # Format message
    msg = f"📊 *Bitcoin Distribution Table*\n"
    msg += f"```\n{'BTC Addresses':<20}{'# BTC Held':<15}{'Today':<12}{'Yesterday':<12}{'Last Month':<12}\n"
    msg += "-" * 70 + "\n"

    for _, row in df.iterrows():
        btc_addresses = row["BTC Addresses"]
        held_today = f"{int(row['# BTC Held Today']):,}"
        today = f"{int(row[f'Today']):+}"
        yesterday = f"{int(row[f'Yesterday']):+}"
        last_month = f"{int(row['Last Month']):+}"

        msg += f"{btc_addresses:<20}{held_today:<15}{today:<12}{yesterday:<12}{last_month:<12}\n"

    msg += "```"

    msg += get_insight(data)

    return msg

def get_distribution():
    df = get_data()
    msg = generate_message(df)
    return msg
