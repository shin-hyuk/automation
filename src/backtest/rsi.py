import pandas as pd
import matplotlib.pyplot as plt

# Load the CSV file
file_path = 'Binance_BTCUSDT_1h.csv'  # Replace with your actual file path
df = pd.read_csv(file_path)

# Debug: Check the first few rows of the dataset
print("First few rows of the dataset:")
print(df.head())

# Handle fractional seconds in the 'Date' column
df['Date'] = df['Date'].str.replace(r'\.\d+', '', regex=True)  # Remove .000
df['Date'] = pd.to_datetime(df['Date'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
df.dropna(subset=['Date'], inplace=True)

# Extract the hour from the 'Date' column
df['Hour'] = df['Date'].dt.hour

# Calculate price change
df['Price_Change'] = df['Close'] - df['Open']

# Calculate RSI
def calculate_rsi(prices, period=14):
    delta = prices.diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

df['RSI'] = calculate_rsi(df['Close'])

# Define 8-hour timeframes
timeframes = [(hour, hour + 8) for hour in range(0, 24, 8)]

# Analyze each 8-hour timeframe
results = []
for start_hour, end_hour in timeframes:
    # Filter data for the timeframe and reset index
    timeframe_data = df[(df['Hour'] >= start_hour) & (df['Hour'] < end_hour)].copy().reset_index(drop=True)

    # Identify where RSI crosses above 30
    timeframe_data['RSI_Below_30'] = timeframe_data['RSI'] < 30
    timeframe_data['RSI_Cross_30'] = (timeframe_data['RSI_Below_30'].shift(1) == True) & (timeframe_data['RSI'] >= 30)

    # Check for success (price increase after RSI crosses 30) and track duration
    successes = 0
    total_crosses = 0
    total_durations = []
    
    for i in timeframe_data.index:
        if timeframe_data.loc[i, 'RSI_Cross_30']:
            total_crosses += 1
            duration = 0
            # Check how long the price continues to increase
            for j in range(i + 1, len(timeframe_data)):
                if timeframe_data.loc[j, 'Price_Change'] > 0:
                    duration += 1
                else:
                    break
            if duration > 0:
                successes += 1
                total_durations.append(duration)

    # Calculate success rate
    success_rate = (successes / total_crosses) * 100 if total_crosses > 0 else 0
    avg_duration = sum(total_durations) / len(total_durations) if total_durations else 0

    # Append results
    results.append({
        'Timeframe': f"{start_hour:02d}:00-{end_hour:02d}:00",
        'Total_Crosses': total_crosses,
        'Successes': successes,
        'Success_Rate': success_rate,
        'Average_Duration': avg_duration
    })

# Convert results to a DataFrame
results_df = pd.DataFrame(results)

# Display the results
print("\nFinal Results:")
print(results_df)

# Plot the success rate by timeframe
plt.figure(figsize=(12, 6))
plt.bar(results_df['Timeframe'], results_df['Success_Rate'], color='blue', alpha=0.7)
plt.title('Success Rate of Reversal After RSI Crosses 30 by 8-Hour Timeframe')
plt.xlabel('8-Hour Timeframe')
plt.ylabel('Success Rate (%)')
plt.xticks(rotation=45)
plt.show()

# Plot the average duration by timeframe
plt.figure(figsize=(12, 6))
plt.bar(results_df['Timeframe'], results_df['Average_Duration'], color='green', alpha=0.7)
plt.title('Average Duration of Price Increase After RSI Crosses 30')
plt.xlabel('8-Hour Timeframe')
plt.ylabel('Average Duration (8-Hour Blocks)')
plt.xticks(rotation=45)
plt.show()
