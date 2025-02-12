from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError
from datetime import datetime, timedelta
import random
import time

CRYPTO_LIST = ['Bitcoin', 'Ethereum', 'XRP', 'Solana', 'Binance']

def get_data():
    pytrends = TrendReq()
    timeframe = 'today 1-m'
    pytrends.build_payload(CRYPTO_LIST, timeframe=timeframe)

    while True:
        try:
            data = pytrends.interest_over_time()
            break
        except TooManyRequestsError:
            sleep_time = random.uniform(5, 10)
            print(f"Too many requests. Sleeping for {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
    
    if 'isPartial' in data.columns:
        data = data.drop(columns=['isPartial'])
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    data = data[(data.index >= start_date) & (data.index <= end_date)]

    return data

def format_with_sign(number):
    return f"{'+' if number > 0 else ''}{number:.2f}"

def get_insight(df):
    normalized_trends = df[CRYPTO_LIST].apply(lambda x: (x / x.max()) * 100, axis=0)

    insights = get_max(normalized_trends)
    insights += "\n" + get_reversal(normalized_trends)
    insights += "\n" + get_sudden_change(normalized_trends)
    insight_list = insights.split("\n")
    msg = "\n".join(f"*{i + 1})* {line}" for i, line in enumerate(insight_list) if line.strip())
    msg += "\n"
    return msg


def get_max(normalized_trends):
    # Use the first row (30 days ago) and the last row (today)
    last_month_values = normalized_trends.iloc[0]
    today_values = normalized_trends.iloc[-1]
    
    # Calculate percentage change over the last month
    last_month_change = ((today_values - last_month_values) / last_month_values) * 100
    
    # Find the max gain and max loss
    max_gain = last_month_change.idxmax()
    max_loss = last_month_change.idxmin()
    
    msg = f"{max_gain} saw the largest increase, gaining *{last_month_change[max_gain]:.2f}%* in popularity over the last month."

    if last_month_change[max_loss] < 0:
        msg += f"\n{max_loss} saw the largest decline, losing *{abs(last_month_change[max_loss]):.2f}%* in popularity over the last month."

    return msg


def get_reversal(normalized_trends):
    df = normalized_trends.diff().iloc[1:].iloc[::-1].iloc[1:]  # Reverse for recent-first order and drop today
    rising_streaks = {}
    falling_streaks = {}

    for crypto in df.columns:
        category_data = df[crypto]

        # Determine yesterday's and the day before yesterday's direction
        yesterday_change = category_data.iloc[0]
        day_before_yesterday_change = category_data.iloc[1]

        yesterday_direction = "rising" if yesterday_change > 0 else "falling" if yesterday_change < 0 else None
        day_before_yesterday_direction = "rising" if day_before_yesterday_change > 0 else "falling" if day_before_yesterday_change < 0 else None

        # Check if there was a reversal yesterday
        if yesterday_direction and day_before_yesterday_direction and yesterday_direction != day_before_yesterday_direction:
            # Start counting the streak for the previous direction
            streak_count = 1
            for change in category_data.iloc[2:]:
                direction = "rising" if change > 0 else "falling" if change < 0 else None
                if direction == day_before_yesterday_direction:
                    streak_count += 1
                else:
                    break  # Stop counting when direction changes
            
            if yesterday_direction == "rising":
                rising_streaks[crypto] = streak_count
            else:
                falling_streaks[crypto] = streak_count

    # Find the longest streaks
    max_rising_streak = max(rising_streaks.values(), default=0)
    max_falling_streak = max(falling_streaks.values(), default=0)

    longest_rising_cryptos = [k for k, v in rising_streaks.items() if v == max_rising_streak]
    longest_falling_cryptos = [k for k, v in falling_streaks.items() if v == max_falling_streak]

    messages = []
    
    if longest_rising_cryptos and max_rising_streak > 1:
        messages.append(
            f"{', '.join(longest_rising_cryptos)} shifted to rising *after {max_rising_streak} days of falling*."
        )
    if longest_falling_cryptos and max_falling_streak > 1:
        messages.append(
            f"{', '.join(longest_falling_cryptos)} shifted to falling *after {max_falling_streak} days of rising*."
        )

    return "\n".join(messages) if messages else "No reversals detected."



def get_sudden_change(normalized_trends, window_size=30, std_multiplier=1):
    # Calculate percentage changes
    df = normalized_trends.pct_change() * 100
    df = df.iloc[1:]  # Drop NaN row caused by pct_change
    yesterday = df.iloc[-2]  # Use yesterday's changes for comparison
    df = df.iloc[-(window_size + 2):-2]  # Focus on the rolling window
    messages = []

    for crypto in df.columns:
        category_data = df[crypto]
        # Separate positive and negative changes
        positive_changes = category_data[category_data > 0]
        negative_changes = abs(category_data[category_data < 0])  # Absolute value for negative changes

        # Calculate mean and threshold for positive changes
        positive_mean = positive_changes.mean()
        positive_std = positive_changes.std()
        positive_threshold = positive_mean + (std_multiplier * positive_std)

        # Calculate mean and threshold for negative changes
        negative_mean = negative_changes.mean()
        negative_std = negative_changes.std()
        negative_threshold = negative_mean + (std_multiplier * negative_std)

        # Check if yesterday's change exceeds the thresholds
        value_yesterday = yesterday[crypto]
        if value_yesterday > 0 and value_yesterday > positive_threshold:
            messages.append(
                f"{crypto} gained *{value_yesterday:.2f}%* in popularity, well above its monthly average of {positive_mean:.2f}%."
            )
        elif value_yesterday < 0 and abs(value_yesterday) > negative_threshold:
            messages.append(
                f"{crypto} declined *{abs(value_yesterday):.2f}%* in popularity, well above its monthly average of {negative_mean:.2f}%."
            )

    return "\n".join(messages) if messages else "No sudden search activity detected."


def get_google_trends():
    trends_data = get_data()
    normalized_trends = trends_data[CRYPTO_LIST].apply(lambda x: (x / x.max()) * 100, axis=0)

    raw_today_values = trends_data[CRYPTO_LIST].iloc[-1] 
    today_values = normalized_trends.iloc[-1]
    yesterday_values = normalized_trends.iloc[-2]
    last_week_values = normalized_trends.iloc[-8]
    last_month_values = normalized_trends.iloc[0]

    shares = {crypto: (value / raw_today_values.sum()) * 100 for crypto, value in raw_today_values.items()}

    msg = f"🔍 *Trending Crypto Searches*\n"
    msg += "```\n"
    msg += f"{'Crypto':<15}{'Search Share':<15}{'Yesterday':<15}{'Last Week':<15}{'Last Month':<15}\n"
    msg += "-" * 71 + "\n"

    for crypto in CRYPTO_LIST:
        share = shares[crypto]

        today = today_values[crypto]
        yesterday = yesterday_values[crypto]
        last_week = last_week_values[crypto]
        last_month = last_month_values[crypto]

        yesterday_change = ((today - yesterday) / yesterday) * 100
        last_week_change = ((today - last_week) / last_week) * 100
        last_month_change = ((today - last_month) / last_month) * 100

        msg += (
            f"{crypto:<15}"
            f"{f'{share:.2f}%':<15}"
            f"{f'{format_with_sign(yesterday_change)}%':<15}"
            f"{f'{format_with_sign(last_week_change)}%':<15}"
            f"{f'{format_with_sign(last_month_change)}%':<15}\n"
        )

    msg += "```"

    msg += get_insight(trends_data)

    return msg

