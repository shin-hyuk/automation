import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import ta
import csv

def knn_moving_average(series, number_of_closest_values, window_size):
    knn_ma = np.full(len(series), np.nan)  
    for i in range(len(series)):
        if i < window_size:
            continue
        window = series.iloc[i - window_size:i]
        target = series.iloc[i]
        distances = np.abs(window - target)
        closest_indices = distances.nsmallest(number_of_closest_values).index
        knn_ma[i] = window.loc[closest_indices].mean()
    return pd.Series(knn_ma, index=series.index)


def pine_rma(series, length):
    rma = np.full(len(series), np.nan)  
    first_valid_idx = series.first_valid_index()
    if first_valid_idx is None:
        return pd.Series(rma, index=series.index)  
    first_valid_pos = series.index.get_loc(first_valid_idx)
    rma[first_valid_pos] = series.iloc[first_valid_pos]
    for i in range(first_valid_pos + 1, len(series)):
        if np.isnan(series.iloc[i]):
            rma[i] = rma[i - 1]  
        else:
            rma[i] = (series.iloc[i] + (rma[i - 1] * (length - 1))) / length  
    return pd.Series(rma, index=series.index)


def wma(series, length):
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)


def print_calculations(data, latest_color_change_value, latest_rsi, latest_ao, latest_average_knn, sign, ao_color, period):
    print(f"\n📊 {period} Calculations ({data.index[-1].date()}):")
    print(f"latest color_change_value: {latest_color_change_value}")
    print(f"RSI for the latest {period.lower()} ({data.index[-1].date()}): {latest_rsi:.2f}")
    print(f"latest AO Value: {sign}{ao_color}")
    print(f"latest Average_KNN: {latest_average_knn:.6f}")

    print(f"\n📊 {period} Keltner Channels Calculation:")
    print(f"Upper Band: {data['Upper'].iloc[-1]:.2f}")
    print(f"Middle Band (Basis): {data['Middle'].iloc[-1]:.2f}")
    print(f"Lower Band: {data['Lower'].iloc[-1]:.2f}")

def fetch_data(ticker, start_date, end_date, interval='1d'):
    return yf.download(ticker, start=start_date, end=end_date, interval=interval)


def compute_hl2(data):
    data["hl2"] = (data["High"] + data["Low"]) / 2
    return data


def calculate_rsi(data):
    close_series = data['Close'].squeeze()
    rsi_indicator = ta.momentum.RSIIndicator(close_series, window=14)
    data['RSI'] = rsi_indicator.rsi()
    return data


def calculate_knn_ma(data, number_of_closest_values, window_size, smoothing_period):
    data["KNN_MA"] = knn_moving_average(data["hl2"], number_of_closest_values, window_size)
    data["Average_KNN"] = pine_rma(data["KNN_MA"], smoothing_period)
    return data


def calculate_wma(data):
    data["kNN_MA_WMA"] = wma(data["KNN_MA"], length=5)
    return data


def calculate_color_change(data):
    data["kNN_MA_col"] = np.where(
        data["kNN_MA_WMA"] > data["kNN_MA_WMA"].shift(1), "Upknn_col", 
        np.where(data["kNN_MA_WMA"] < data["kNN_MA_WMA"].shift(1), "Dnknn_col", "Neuknn_col")
    )
    data["knnMA_prev_col"] = data["kNN_MA_col"].shift(1)
    data["color_change"] = (data["kNN_MA_col"] != data["knnMA_prev_col"]) & (data["kNN_MA_WMA"].notna())
    data["color_change_value"] = np.where(
        (data["color_change"]) & (data["kNN_MA_col"] == "Upknn_col"), 1.0, 
        np.where((data["color_change"]) & (data["kNN_MA_col"] == "Dnknn_col"), 0.0, np.nan)
    )
    data["color_change_value"] = data["color_change_value"].ffill()
    return data


def calculate_keltner_channels(data, length, mult, atrlength, use_exp_ma, bands_style):
    if use_exp_ma:
        data["Middle"] = data["Close"].ewm(span=length, adjust=False).mean()  
    else:
        data["Middle"] = data["Close"].rolling(window=length).mean()  

    data["High-Low"] = data["High"] - data["Low"]
    data["High-Close"] = abs(data["High"] - data["Close"].shift(1))
    data["Low-Close"] = abs(data["Low"] - data["Close"].shift(1))
    data["True Range"] = data[["High-Low", "High-Close", "Low-Close"]].max(axis=1)

    if bands_style == "True Range":
        data["RangeMA"] = data["True Range"]
    elif bands_style == "Average True Range":
        data["RangeMA"] = data["True Range"].rolling(window=atrlength).mean()
    else:  
        data["RangeMA"] = data["High-Low"].rolling(window=length).mean()

    data["Upper"] = data["Middle"] + (data["RangeMA"] * mult)
    data["Lower"] = data["Middle"] - (data["RangeMA"] * mult)

    return data


def calculate_ao(data):
    sma_5 = data['hl2'].rolling(window=5).mean()
    sma_34 = data['hl2'].rolling(window=34).mean()
    data['AO'] = sma_5 - sma_34
    data['diff'] = data['AO'].diff()  # Change in AO
    return data


def get_latest_values(data):
    latest_rsi = data['RSI'].iloc[-1]
    latest_average_knn = data['Average_KNN'].iloc[-1]
    latest_color_change_numeric = data['color_change_value'].iloc[-1]
    latest_color_change_value = "Green" if latest_color_change_numeric == 1.0 else "Red"
    latest_ao = data['AO'].iloc[-1]
    latest_diff = data['diff'].iloc[-1]
    sign = "+" if latest_ao > 0 else "-"
    ao_color = "Green" if latest_diff > 0 else "Red"
    return latest_rsi, latest_average_knn, latest_color_change_value, latest_ao, sign.replace('+', '(+)').replace('-', '(-)'), ao_color


def write_to_csv_with_skipped_columns_horizontal(filename, date, tickers, day_values_list, week_values_list):
    # Prepare the data in groups of 4 assets
    grouped_data = []
    for start in range(0, len(tickers), 4):
        end = min(start + 4, len(tickers))
        date_row = []
        header = []
        asset_row = []  # Reintroduce asset row
        data_rows = [[] for _ in range(9)]  # 8 metrics + 1 opinion
        for i in range(start, end):
            if i >= len(day_values_list) or i >= len(week_values_list):
                continue
            date_row.extend(['', date, '', ''])  # Add space between groups
            header.extend(['Metric', 'Day', 'Week', ''])  # Keep original format
            asset_row.extend(['Asset', tickers[i], tickers[i], ''])  # Add asset names
            keys = ['color_change', 'rsi', 'ao', 'ao_sign', 'avg_knn', 'kc_upper', 'kc_middle', 'kc_lower']
            for j, key in enumerate(keys):
                day_value = day_values_list[i].get(key, '')
                week_value = week_values_list[i].get(key, '')
                # Round numerical values to two decimal places
                day_value = f'{day_value:.2f}' if isinstance(day_value, (int, float)) else day_value
                week_value = f'{week_value:.2f}' if isinstance(week_value, (int, float)) else week_value
                data_rows[j].extend([
                    key.replace('_', ' ').title(),
                    day_value,
                    week_value,
                    ''  # Add space between groups
                ])
            # Add opinion row
            data_rows[8].extend(['Opinion', '', '', ''])
        grouped_data.append([date_row, header, asset_row] + data_rows)  # Include asset_row

    # Write to CSV
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        for group in grouped_data:
            writer.writerows(group)
            writer.writerow([])  # Add an empty row between groups


def process_asset(ticker, start_date, end_date, interval='1d'):
    try:
        data = fetch_data(ticker, start_date, end_date, interval)
        if data.empty:
            print(f"No data for {ticker}. Skipping.")
            return None
        data = compute_hl2(data)
        data = calculate_rsi(data)
        data = calculate_knn_ma(data, number_of_closest_values=3, window_size=30, smoothing_period=50)
        data = calculate_wma(data)
        data = calculate_color_change(data)
        data = calculate_keltner_channels(data, length=20, mult=2.0, atrlength=10, use_exp_ma=True, bands_style="Average True Range")
        data = calculate_ao(data)
        latest_rsi, latest_average_knn, latest_color_change_value, latest_ao, sign, ao_color = get_latest_values(data)
        return {
            'color_change': latest_color_change_value,
            'rsi': latest_rsi,
            'ao': ao_color,
            'ao_sign': sign,
            'avg_knn': latest_average_knn,
            'kc_upper': data['Upper'].iloc[-1],
            'kc_middle': data['Middle'].iloc[-1],
            'kc_lower': data['Lower'].iloc[-1]
        }
    except Exception as e:
        print(f"Error processing {ticker}: {e}")
        return None


# Main Execution Logic

tickers = ["AAPL", "TSLA", "NU", "QQQ", "COIN", "V", "GOOGL", "MA", "MSTR", "VYM", "VOO", "UNH", "PG", "JPM", "PFE", "BRK-B", "BRK-A"]

# Limit the number of assets to process to 100
max_assets = 100

# Main Execution Logic
end_date = datetime.now().strftime('%Y-%m-%d')  # Use current date

all_day_values = []
all_week_values = []

# Process only up to max_assets
for ticker in tickers[:max_assets]:
    # Daily calculations
    day_values = process_asset(ticker, "2022-01-01", end_date)
    if day_values:
        all_day_values.append(day_values)

    # Weekly calculations
    week_values = process_asset(ticker, "2022-01-01", end_date, interval="1wk")
    if week_values:
        all_week_values.append(week_values)

# Use the new function to write to CSV
file_name = f'Stock_analysis_{end_date}.csv'
write_to_csv_with_skipped_columns_horizontal(file_name, end_date, tickers, all_day_values, all_week_values)
