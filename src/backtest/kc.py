import ccxt
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Initialize the exchange (e.g., Binance)
exchange = ccxt.binance()

# Parameters
symbol = 'BTC/USDT'  # Trading pair
timeframe = '4h'      # Timeframe for candles (4 hours)
ema_length = 20       # EMA period (length)
atr_length = 10       # ATR period (length)
atr_multiplier = 2    # ATR multiplier for Keltner Channels
stop_loss_percentage = 0.01  # Stop loss percentage (1%)
limit = 365 * 6       # Fetch 1 year of 4-hour data (365 days * 6 candles per day)

def fetch_ohlcv(symbol, timeframe, limit):
    """Fetch OHLCV data from the exchange."""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_ema(data, period):
    """Calculate Exponential Moving Average (EMA) using pandas."""
    return data['close'].ewm(span=period, adjust=False).mean()

def calculate_atr(data, period):
    """Calculate Average True Range (ATR) using pandas."""
    high_low = data['high'] - data['low']
    high_close = np.abs(data['high'] - data['close'].shift())
    low_close = np.abs(data['low'] - data['close'].shift())
    true_range = np.maximum(high_low, np.maximum(high_close, low_close))
    atr = true_range.rolling(window=period).mean()
    return atr

def calculate_keltner_channels(df, ema_length, atr_length, atr_multiplier):
    """Calculate Keltner Channels."""
    df['ema'] = calculate_ema(df, ema_length)  # EMA based on close price
    df['atr'] = calculate_atr(df, atr_length)  # ATR with specified length
    df['upper_kc'] = df['ema'] + atr_multiplier * df['atr']
    df['lower_kc'] = df['ema'] - atr_multiplier * df['atr']
    return df

def backtest_strategy(df):
    """Backtest the strategy."""
    df['signal'] = 0  # 0 = no signal, 1 = buy, -1 = sell
    open_trades = []  # Track open trades

    for i in range(1, len(df)):
        # Buy Signal: Close price touches Lower KC
        if df['close'][i] <= df['lower_kc'][i]:
            entry_price = df['close'][i]  # Set entry price
            stop_loss = entry_price * (1 - stop_loss_percentage)  # Set stop loss 1% below buy price
            target = df['ema'][i]  # First target is EMA
            open_trades.append({
                'entry_index': i,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'target': target,
                'status': 'open'
            })
            df.at[df.index[i], 'signal'] = 1  # Buy signal
            print(f"Buy Signal at {df['timestamp'][i]}: Price = {entry_price}, Stop Loss = {stop_loss}, Target = {target}")

        # Check open trades
        for trade in open_trades:
            if trade['status'] == 'open':
                # First Target Reached: EMA is reached
                if df['close'][i] >= trade['target']:
                    trade['stop_loss'] = df['ema'][i]  # Update stop loss to EMA
                    trade['target'] = df['upper_kc'][i]  # New target is Upper KC
                    print(f"First Target Reached at {df['timestamp'][i]}: New Stop Loss = {trade['stop_loss']}, New Target = {trade['target']}")

                # Sell Signal: Close price reaches Upper KC or hits stop loss
                if df['close'][i] >= trade['target'] or df['close'][i] <= trade['stop_loss']:
                    trade['status'] = 'closed'
                    trade['exit_price'] = df['close'][i]  # Set exit price
                    profit = (trade['exit_price'] - trade['entry_price']) / trade['entry_price'] * 100  # Calculate profit/loss
                    df.at[df.index[i], 'signal'] = -1  # Sell signal
                    print(f"Sell Signal at {df['timestamp'][i]}: Price = {trade['exit_price']}, Profit/Loss = {profit:.2f}%")

    # Close any remaining open trades at the end of the data
    for trade in open_trades:
        if trade['status'] == 'open':
            trade['status'] = 'closed'
            trade['exit_price'] = df['close'].iloc[-1]  # Set exit price to the last close price
            profit = (trade['exit_price'] - trade['entry_price']) / trade['entry_price'] * 100  # Calculate profit/loss
            df.at[df.index[-1], 'signal'] = -1  # Sell signal
            print(f"Trade Closed at {df['timestamp'].iloc[-1]}: Price = {trade['exit_price']}, Profit/Loss = {profit:.2f}%")

    return df, open_trades

def calculate_performance(open_trades):
    """Calculate performance metrics."""
    closed_trades = [trade for trade in open_trades if trade['status'] == 'closed']
    total_trades = len(closed_trades)
    winning_trades = len([trade for trade in closed_trades if (trade['exit_price'] - trade['entry_price']) / trade['entry_price'] * 100 > 0])
    losing_trades = len([trade for trade in closed_trades if (trade['exit_price'] - trade['entry_price']) / trade['entry_price'] * 100 < 0])
    win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
    total_profit = sum((trade['exit_price'] - trade['entry_price']) / trade['entry_price'] * 100 for trade in closed_trades if (trade['exit_price'] - trade['entry_price']) / trade['entry_price'] * 100 > 0)
    total_loss = sum((trade['exit_price'] - trade['entry_price']) / trade['entry_price'] * 100 for trade in closed_trades if (trade['exit_price'] - trade['entry_price']) / trade['entry_price'] * 100 < 0)
    average_profit_per_trade = total_profit / winning_trades if winning_trades > 0 else 0
    average_loss_per_trade = total_loss / losing_trades if losing_trades > 0 else 0

    print(f"Total Trades: {total_trades}")
    print(f"Winning Trades: {winning_trades}")
    print(f"Losing Trades: {losing_trades}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Total Profit: {total_profit:.2f}%")
    print(f"Total Loss: {total_loss:.2f}%")
    print(f"Average Profit per Trade: {average_profit_per_trade:.2f}%")
    print(f"Average Loss per Trade: {average_loss_per_trade:.2f}%")

def main():
    """Main function to fetch data, backtest, and calculate performance."""
    # Fetch OHLCV data
    print("Fetching real-time 4-hour data for the past year...")
    df = fetch_ohlcv(symbol, timeframe, limit)

    # Calculate Keltner Channels
    print("Calculating Keltner Channels...")
    df = calculate_keltner_channels(df, ema_length, atr_length, atr_multiplier)

    # Plot Keltner Channels for debugging
    plt.figure(figsize=(14, 7))
    plt.plot(df['timestamp'], df['close'], label='Close Price', color='blue')
    plt.plot(df['timestamp'], df['ema'], label=f'{ema_length}-Period EMA', color='orange')
    plt.plot(df['timestamp'], df['upper_kc'], label='Upper Keltner Channel', color='green', linestyle='--')
    plt.plot(df['timestamp'], df['lower_kc'], label='Lower Keltner Channel', color='red', linestyle='--')
    plt.fill_between(df['timestamp'], df['upper_kc'], df['lower_kc'], color='gray', alpha=0.3)
    plt.title(f'Keltner Channels (EMA {ema_length}, ATR {atr_length}, Multiplier {atr_multiplier}) for {symbol}')
    plt.xlabel('Time')
    plt.ylabel('Price')
    plt.legend()
    plt.show()

    # Backtest the strategy
    print("Backtesting the strategy...")
    df, open_trades = backtest_strategy(df)

    # Calculate performance metrics
    print("Calculating performance metrics...")
    calculate_performance(open_trades)

if __name__ == "__main__":
    main()