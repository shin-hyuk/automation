import asyncio
import pandas as pd
import ccxt
from telegram import Bot
from datetime import datetime, timedelta


# Initialize Binance Exchange with time adjustment
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True,  # Automatically adjust for time difference
    },
})

# Define COIN_DATA for Aggressive Investors
AGGRESSIVE_COIN_DATA = {
    'BTC/USDT': {'win_rate': 58, 'avg_profit': 9.39, 'avg_loss': 4.58, 'holding_days': 7, 'window_size': 10, 'std_multiplier': 2.5},
    'ETH/USDT': {'win_rate': 55, 'avg_profit': 14.51, 'avg_loss': 7.7, 'holding_days': 7, 'window_size': 20, 'std_multiplier': 2.5},
    'SOL/USDT': {'win_rate': 59, 'avg_profit': 14.57, 'avg_loss': 10.9, 'holding_days': 5, 'window_size': 30, 'std_multiplier': 2.0},
    'DOGE/USDT': {'win_rate': 52, 'avg_profit': 23.03, 'avg_loss': 6.75, 'holding_days': 7, 'window_size': 10, 'std_multiplier': 2.5},
}

# Define COIN_DATA for Balanced Investors
BALANCED_COIN_DATA = {
    'BTC/USDT': {'win_rate': 69, 'avg_profit': 6.42, 'avg_loss': 5.5, 'holding_days': 6, 'window_size': 10, 'std_multiplier': 2.5},
    'ETH/USDT': {'win_rate': 60, 'avg_profit': 8.11, 'avg_loss': 6.42, 'holding_days': 4, 'window_size': 20, 'std_multiplier': 2.5},
    'SOL/USDT': {'win_rate': 58, 'avg_profit': 16.04, 'avg_loss': 13.4, 'holding_days': 6, 'window_size': 30, 'std_multiplier': 2.0},
    'DOGE/USDT': {'win_rate': 52, 'avg_profit': 20.0, 'avg_loss': 6.0, 'holding_days': 5, 'window_size': 10, 'std_multiplier': 2.0},
}



# Function to calculate Kelly Fraction
def calculate_kelly_fraction(win_rate, avg_profit, avg_loss):
    win_rate_decimal = win_rate / 100  # Convert percentage to decimal
    if avg_profit > 0 and avg_loss > 0:
        return win_rate_decimal - (1 - win_rate_decimal) * (avg_loss / avg_profit)
    return 0

# Function to calculate Profitability Index
def calculate_profitability_index(win_rate, avg_profit, avg_loss):
    win_rate_decimal = win_rate / 100  # Convert percentage to decimal
    loss_rate_decimal = 1 - win_rate_decimal
    return (win_rate_decimal * avg_profit) + (loss_rate_decimal * avg_loss)

# Function to fetch OHLCV data for a given symbol
async def fetch_ohlcv(symbol, limit):
    try:
        # Fetch OHLCV data from Binance
        ohlcv = await asyncio.to_thread(exchange.fetch_ohlcv, symbol, timeframe='1d', limit=limit)
        return ohlcv
    except Exception as e:
        print(f"Error fetching OHLCV for {symbol}: {e}")
        return None

# Function to detect volume outliers based on a given window size
def detect_volume_outliers(df, window_size, std_multiplier):
    if len(df) < window_size:
        raise ValueError(f"Not enough data to analyze the past {window_size} days.")

    df = df.sort_values(by='Date')

    # Calculate rolling mean and standard deviation for the given window size
    df['Volume_Mean'] = df['volume'].rolling(window=window_size).mean()
    df['Volume_Std'] = df['volume'].rolling(window=window_size).std()
    df['Volume_Threshold'] = df['Volume_Mean'] + std_multiplier * df['Volume_Std']
    df['Volume_Outlier'] = df['volume'] > df['Volume_Threshold']

    yesterday = (datetime.now() - timedelta(days=1)).date()
    yesterday_row = df[df['Date'] == pd.Timestamp(yesterday)]

    return yesterday_row.iloc[0]

# Asynchronous function to monitor symbols for volume outliers day by day
async def monitor_symbols(symbols, coin_data, investor_type):
    for symbol in symbols:
        try:
            # Get the coin-specific settings
            data = coin_data.get(symbol, {})
            window_size = data['window_size']  # Use the specific window_size for this coin
            std_multiplier = data['std_multiplier']  # Use the specific std_multiplier for this coin

            # Fetch OHLCV data for the specified window size
            ohlcv = await fetch_ohlcv(symbol, limit=window_size + 10)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['Date'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df[['Date', 'volume']]  # Keep only relevant columns

            yesterday_row = detect_volume_outliers(df, window_size, std_multiplier)

            #if not yesterday_row['Volume_Outlier']:
            if yesterday_row['Volume_Outlier']:
                volume = yesterday_row['volume']
                threshold = yesterday_row['Volume_Threshold']

                # Calculate metrics
                kelly_fraction = calculate_kelly_fraction(data['win_rate'], data['avg_profit'], data['avg_loss'])
                profitability_index = calculate_profitability_index(data['win_rate'], data['avg_profit'], data['avg_loss'])

                msg = (
                    f"*{symbol}: {std_multiplier}x Volume Spike Detected*"
                    f"\nRecommended Hold: {data['holding_days']} days"
                    f"\nWin Rate: {data['win_rate']}% | Kelly Fraction: {kelly_fraction:.2f} | Profitability Index: {profitability_index:.2f}"
                    f"\nInvestor Profile: {investor_type}"
                )
                return msg

        except Exception as e:
            print(f"Error occurred for {symbol}: {e}")
        
        return

# Main function to monitor multiple symbols
async def get_volume_outlier():
    balanced =  await monitor_symbols(list(BALANCED_COIN_DATA.keys()), BALANCED_COIN_DATA, investor_type="Balanced")
    aggressive =  await monitor_symbols(list(AGGRESSIVE_COIN_DATA.keys()), AGGRESSIVE_COIN_DATA, investor_type="Aggressive")

    msg = ""
    if balanced:
        msg += f"\n{balanced}"

    """
    if aggressive:
        msg += f"\n\n{aggressive}"
    """
    
    return msg