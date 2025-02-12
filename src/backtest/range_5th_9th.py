import pandas as pd
import matplotlib.pyplot as plt


# Function to calculate the drop, ensuring dates are within range
def calculate_drop(group):
    max_drop = 0
    peak_price = None
    peak_time = None
    trough_price = None
    trough_time = None
    
    # Iterate through each bar (candle) in the group
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            # Get the high price (peak) and low price (trough)
            peak = group.iloc[i]
            trough = group.iloc[j]
            
            # Confirm the peak is before the trough in time and dates are valid
            if peak['time'] < trough['time']:
                # Calculate the percentage drop
                drop = (trough['low'] - peak['high']) / peak['high'] * 100
                
                # Update the maximum drop if the new drop is larger
                if drop < max_drop:
                    max_drop = drop
                    peak_price = peak['high']
                    peak_time = peak['time']
                    trough_price = trough['low']
                    trough_time = trough['time']

    return max_drop, peak_price, peak_time, trough_price, trough_time


def test_5th_9th():
    # Load the new CSV file
    file_path = './src/trade/BINANCE_BTCUSDT, 1D.csv'  # Replace with your actual file path
    df = pd.read_csv(file_path)

    # Convert the 'time' column to datetime
    df['time'] = pd.to_datetime(df['time'])

    # Add Year, Month, and Day columns for filtering
    df['Year'] = df['time'].dt.year
    df['Month'] = df['time'].dt.month
    df['Day'] = df['time'].dt.day

    # Filter data for the 4th to the 9th of each month in 2024
    df_filtered = df[(df['Year'] == 2024) & (df['Day'] >= 4) & (df['Day'] <= 9)]

    # Group data by month and calculate peak-to-trough drop
    results = []
    for month, group in df_filtered.groupby('Month'):  # Group by month
        group = group.sort_values(by='time')  # Ensure data is sorted by time
        
        # Calculate the maximum drop for the current group
        max_drop, peak_price, peak_time, trough_price, trough_time = calculate_drop(group)
        
        results.append({
            'Month': month,
            'Max_Peak_to_Trough_Drop (%)': max_drop,
            'Peak_Price': peak_price,
            'Peak_Time': peak_time,
            'Trough_Price': trough_price,
            'Trough_Time': trough_time
        })

    # Convert results to a DataFrame
    results_df = pd.DataFrame(results)

    # Display results
    print("\nMaximum Peak-to-Trough Drop and Time Ranges from 4th to 9th for Each Month (2024):")

    # Plot the results
    plt.figure(figsize=(10, 6))
    plt.bar(results_df['Month'], results_df['Max_Peak_to_Trough_Drop (%)'], color='blue', alpha=0.7)
    plt.axhline(y=-3, color='red', linestyle='--', label='3% Drop Threshold')
    plt.title('Maximum Peak-to-Trough Drop (4th to 9th) by Month (2024)')
    plt.xlabel('Month')
    plt.ylabel('Peak-to-Trough Drop (%)')
    plt.xticks(results_df['Month'])
    plt.legend()
    plt.show()

    return
