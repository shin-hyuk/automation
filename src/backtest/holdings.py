import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from btc.get_distribution import get_data_since as get_distribution

def get_price(start_date):
    price_data_path = './src/trade/BINANCE_BTCUSDT, 1D.csv'
    price_df = pd.read_csv(price_data_path)
    price_df.rename(columns={'time': 'Date', 'close': 'Price'}, inplace=True)
    price_df['Date'] = pd.to_datetime(price_df['Date'], format='%Y-%m-%d')
    price_df = price_df[['Date', 'Price']]  # Keep only necessary columns

    # Filter for data after the start_date
    start_date = pd.to_datetime(start_date)
    price_df = price_df[price_df['Date'] >= start_date].reset_index(drop=True)

    return price_df

def analyze_distributions(start_date, window_size, std):

    df = get_distribution(start_date)

    # Convert 'Date' to datetime for plotting
    df['Date'] = pd.to_datetime(df['Date'])

    # Calculate percentage changes for each distribution
    distribution_columns = ['100+ BTC']
    # distribution_columns = ['0.001 - 1 BTC', '1 - 10 BTC', '10 - 100 BTC', '100+ BTC']

    for column in distribution_columns:
        df[f'{column}_Pct_Change'] = df[column].pct_change() * 100

    # Define thresholds for sudden changes
    outlier_list = []  # To track all outliers with their indices

    for column in distribution_columns:
        df[f'{column}_Outlier'] = False  # Initialize the outlier column

        for idx in range(len(df)):
            # Define rolling window bounds
            start_idx = max(0, idx - window_size + 1)
            rolling_window = df.iloc[start_idx:idx + 1]

            # Calculate mean and standard deviation for absolute percentage changes
            rolling_mean = rolling_window[f'{column}_Pct_Change'].abs().mean()
            rolling_std = rolling_window[f'{column}_Pct_Change'].abs().std()

            # Check if the current value is an outlier using its absolute percentage change
            current_pct_change = df.loc[idx, f'{column}_Pct_Change']
            is_outlier = (
                abs(current_pct_change) > rolling_mean + std * rolling_std
            )

            if is_outlier:
                # Find existing outliers in the rolling window
                existing_outliers_in_window = [
                    outlier for outlier in outlier_list if start_idx <= outlier['index'] <= idx
                ]

                # Include the current potential outlier in the list for comparison
                candidate_outliers = existing_outliers_in_window + [{'index': idx, 'Date': df.loc[idx, 'Date'], 'Pct_Change': current_pct_change}]

                # Identify the most recent outlier among those in the window
                most_old_outlier = min(candidate_outliers, key=lambda x: x['Date'])

                # Update the outlier list to exclude older outliers in the window
                outlier_list = [
                    outlier for outlier in outlier_list if not (start_idx <= outlier['index'] <= idx)
                ]
                outlier_list.append(most_old_outlier)

                # Mark the most recent outlier in the dataframe
                df.loc[most_old_outlier['index'], f'{column}_Outlier'] = True

    return df, outlier_list



def analyze_price(start_date, window_size, std):
    # Get the price data
    price_df = get_price(start_date)

    # Analyze distributions and get outliers
    distribution_df, outlier_list = analyze_distributions(start_date, window_size, std)

    # Merge price and distribution data
    combined_df = price_df.merge(distribution_df[['Date']], on='Date', how='inner')

    # Initialize results
    results = []

    # Analyze price changes after each outlier
    for outlier in outlier_list:
        idx = outlier['index']
        date = outlier['Date']
        pct_change = outlier['Pct_Change']

        # Ensure sufficient data exists for calculation
        if idx + 7 < len(combined_df):
            price_after = {
                f'Price_After_{i}_Days': combined_df.loc[idx + i, 'Price'] / combined_df.loc[idx, 'Price'] - 1
                for i in range(1, 8)
            }
        else:
            price_after = {f'Price_After_{i}_Days': None for i in range(1, 8)}

        # Append to results
        results.append({
            'Date': date,
            'Pct_Change': pct_change,
            **price_after
        })

    # Convert results to DataFrame
    results_df = pd.DataFrame(results)

    if results_df.empty:
        return None

    # Calculate EV for buyers (positive Pct_Change)
    buyers_df = results_df[results_df['Pct_Change'] > 0]
    buyers_avg_return = buyers_df.iloc[:, 2:].mean()
    buyers_win_rate = (buyers_df.iloc[:, 2:] > 0).mean()
    buyers_ev = {
        col: buyers_avg_return[col] * buyers_win_rate[col] if buyers_win_rate[col] > 0 else None
        for col in buyers_avg_return.index
    }

    # Calculate EV for sellers (negative Pct_Change)
    sellers_df = results_df[results_df['Pct_Change'] < 0]
    sellers_avg_return = sellers_df.iloc[:, 2:].mean()
    sellers_win_rate = (sellers_df.iloc[:, 2:] > 0).mean()
    sellers_ev = {
        col: sellers_avg_return[col] * sellers_win_rate[col] if sellers_win_rate[col] > 0 else None
        for col in sellers_avg_return.index
    }

    # Add EV rows for buyers and sellers to the results DataFrame
    buyers_ev_row = {
        'Date': 'Big Whales Buy (EV)',
        'Pct_Change': 'N/A',
        **buyers_ev,
    }
    sellers_ev_row = {
        'Date': 'Big Whales Sell (EV)',
        'Pct_Change': 'N/A',
        **sellers_ev,
    }

    results_df = pd.concat(
        [results_df, pd.DataFrame([buyers_ev_row, sellers_ev_row])],
        ignore_index=True
    )

    return results_df



def test_holdings(start_date):
    window_sizes = [10, 15, 30, 45]
    std_devs = [1.5, 2, 2.5, 3]

    # Variable to track the highest EV and its corresponding results
    highest_ev = -float('inf')
    highest_ev_df = None
    highest_ev_combo = None  # Track the best window_size and std_dev combination
    highest_ev_category = None  # Track whether it was Buyers or Sellers

    for window_size in window_sizes:
        for std_dev in std_devs:
            print(f"Testing with window_size={window_size}, std_dev={std_dev}")
            results_df = analyze_price(start_date, window_size, std_dev)

            if results_df is None:
                continue

            # Extract EV values for Buyers and Sellers
            buyers_ev_values = results_df[results_df['Date'] == 'Big Whales Buy (EV)'][[
                'Price_After_1_Days', 'Price_After_2_Days', 'Price_After_3_Days',
                'Price_After_4_Days', 'Price_After_5_Days', 'Price_After_6_Days', 'Price_After_7_Days'
            ]].values.flatten()  # Flatten to 1D array
            sellers_ev_values = results_df[results_df['Date'] == 'Big Whales Sell (EV)'][[
                'Price_After_1_Days', 'Price_After_2_Days', 'Price_After_3_Days',
                'Price_After_4_Days', 'Price_After_5_Days', 'Price_After_6_Days', 'Price_After_7_Days'
            ]].values.flatten()

            # Determine the maximum EV for Buyers
            if buyers_ev_values.size > 0 and buyers_ev_values.max() > highest_ev:
                highest_ev = buyers_ev_values.max()  # Update the highest EV
                highest_ev_df = results_df.copy()   # Save the corresponding DataFrame
                highest_ev_combo = (window_size, std_dev)  # Save the combination
                highest_ev_category = 'Big Whales Buy'

            # Determine the maximum EV for Sellers
            if sellers_ev_values.size > 0 and sellers_ev_values.max() > highest_ev:
                highest_ev = sellers_ev_values.max()  # Update the highest EV
                highest_ev_df = results_df.copy()   # Save the corresponding DataFrame
                highest_ev_combo = (window_size, std_dev)  # Save the combination
                highest_ev_category = 'Big Whales Sell'

    # Save the results to CSV and plot the EV bar chart
    if highest_ev_df is not None:
        best_window, best_std = highest_ev_combo
        filename = f'bitcoin_distribution_backtest.csv'
        highest_ev_df.to_csv(filename, index=False)
        print(f"Saved highest EV results to CSV: {filename}")

        # Plot the EV values for the highest combination
        ev_values = highest_ev_df[highest_ev_df['Date'] == f'{highest_ev_category} (EV)'][[
            'Price_After_1_Days', 'Price_After_2_Days', 'Price_After_3_Days',
            'Price_After_4_Days', 'Price_After_5_Days', 'Price_After_6_Days', 'Price_After_7_Days'
        ]].values.flatten()

        # Calculate the average EV value
        average_ev = ev_values.mean()

        # Create the bar chart
        plt.figure(figsize=(10, 6))
        days = [f'Day {i}' for i in range(1, 8)]
        plt.bar(days, ev_values, color='skyblue', label='EV Values')

        # Add a dotted line for the average EV
        plt.axhline(y=average_ev, color='red', linestyle='--', label=f'Average EV: {average_ev:.4f}')

        # Customize the chart
        plt.title(f'EV Values after {highest_ev_category} (Window={best_window}, Std={best_std})')
        plt.xlabel('Days')
        plt.ylabel('Expected Value (EV)')
        plt.legend()
        plt.tight_layout()

        # Show the plot
        plt.show()
