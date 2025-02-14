import time
import random
import pymysql
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from dotenv import load_dotenv
import os
import docker
from time import sleep
import pandas as pd

# Load environment variables
load_dotenv()

# MySQL Connection Details from .env
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_PORT = int(os.getenv('DB_PORT', 3306))

# Entity configurations
ENTITIES = {
    "worldliberty": {
        "url": "https://intel.arkm.com/explorer/entity/worldlibertyfi",
        "table": "worldliberty_holdings",
        "emoji": "🦅",
        "title": "World Liberty Fi"
    },
    "blackrock": {
        "url": "https://intel.arkm.com/explorer/entity/blackrock",
        "table": "blackrock_holdings",
        "emoji": "🏛️",
        "title": "BlackRock"
    },
    "usg": {
        "url": "https://intel.arkm.com/explorer/entity/usg",
        "table": "usg_holdings",
        "emoji": "🏦",
        "title": "US Government"
    }
}

# **Rotating User Agents**
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/110.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

DEFAULT_ASSETS = {"ETH", "WETH"}

# **📌 Connect to MySQL**
def connect_to_database():
    """Connect to MySQL database."""
    try:
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"❌ MySQL Connection Error: {e}")
        return None

# **📌 Initialize Database**
def initialize_database(entity_config, html_content=None):
    """Initialize database with dynamic columns for all cryptocurrencies."""
    connection = connect_to_database()
    if not connection:
        return

    try:
        with connection.cursor() as cursor:
            # Create table if it doesn't exist
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {entity_config['table']} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date DATE NOT NULL UNIQUE,
                    total_value DECIMAL(20,4)
                )
            """)
            connection.commit()
            print(f"Base table {entity_config['table']} is ready")
            
            # Get all possible cryptocurrencies from the webpage
            if not html_content:
                return
            
            soup = BeautifulSoup(html_content, "html.parser")
            holdings_containers = soup.find_all("div", class_="Portfolio_holdingsContainer__XyaUq")
            crypto_columns = set()
            
            for container in holdings_containers:
                symbol_span = container.find("span", class_="Portfolio_holdingsSymbol__uOpkQ")
                if symbol_span:
                    symbol = symbol_span.get_text(strip=True)
                    crypto_columns.add(symbol)
            
            # Get existing columns
            cursor.execute(f"SHOW COLUMNS FROM {entity_config['table']}")
            existing_columns = {row['Field'] for row in cursor.fetchall()}
            
            # Add any new cryptocurrencies as columns
            for symbol in crypto_columns:
                if symbol not in existing_columns:
                    print(f"Adding new column for {symbol}")
                    try:
                        cursor.execute(f"""
                            ALTER TABLE {entity_config['table']}
                            ADD COLUMN `{symbol}` DECIMAL(20,4)
                        """)
                        connection.commit()
                    except Exception as e:
                        print(f"Error adding column {symbol}: {e}")
            
            print(f"Table {entity_config['table']} is ready with all crypto columns")
            
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        connection.close()

# **📌 Fetch Data with Selenium**
def fetch_data_with_firefox():
    """Fetch data using Selenium in Docker container."""
    container_name = "selenium-firefox"
    image_name = "selenium/standalone-firefox"
    max_retries = 10
    success = False
    retries = 0
    driver = None

    try:
        # Clean up any existing container first
        client = docker.from_env()
        try:
            container = client.containers.get(container_name)
            print(f"Found existing container {container_name}, removing it...")
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            print(f"No existing container {container_name} found")

        # Start Docker container
        print(f"Starting new {container_name} container...")
        client.containers.run(
            image_name,
            name=container_name,
            ports={"4444/tcp": 4444},
            detach=True,
        )
        print("Docker container started")

        while not success and retries < max_retries:
            try:
                options = webdriver.FirefoxOptions()
                options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
                options.add_argument("--headless")
                
                driver = webdriver.Remote(
                    command_executor="http://localhost:4444/wd/hub",
                    options=options
                )
                success = True
            except Exception as e:
                print(f"Error initializing WebDriver: {e}")
                retries += 1
                sleep_time = random.randint(1, 10)
                print(f"Attempt {retries}/{max_retries}")
                time.sleep(sleep_time)

        if not success:
            return None

        print("Launching Firefox Browser...")
        driver.get(URL)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "Portfolio_holdingsContainer__XyaUq"))
        )
        time.sleep(5)

        print("Page Loaded. Extracting content...")
        return driver.page_source

    except Exception as e:
        print(f"Firefox Error: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# **📌 Extract Data**
def extract_holdings_and_value(html_content):
    """Extract holdings and value from HTML content."""
    if not html_content:
        print("No HTML content to parse")
        return None, None

    soup = BeautifulSoup(html_content, "html.parser")
    holdings_data = {}
    processed_symbols = set()

    # Get total value from header
    total_value_element = soup.find("span", class_="Header_portfolioValue__AemOW")
    total_value = total_value_element.get_text(strip=True) if total_value_element else "N/A"

    # Find all holdings containers
    holdings_containers = soup.find_all("div", class_="Portfolio_holdingsContainer__XyaUq")
    print(f"Found {len(holdings_containers)} holdings containers")

    for container in holdings_containers:
        try:
            # Get symbol first
            symbol_span = container.find("span", class_="Portfolio_holdingsSymbol__uOpkQ")
            if not symbol_span:
                continue
            symbol = symbol_span.get_text(strip=True)

            # Skip if we've already processed this symbol
            if symbol in processed_symbols:
                continue

            # Get amount (first span in container)
            amount_span = container.find("span")
            if not amount_span:
                continue
            amount_text = amount_span.get_text(strip=True)

            # Convert B/M/K/T values to full numbers
            try:
                if amount_text.endswith('T'):
                    amount = float(amount_text[:-1]) * 1_000_000_000_000
                elif amount_text.endswith('B'):
                    amount = float(amount_text[:-1]) * 1_000_000_000
                elif amount_text.endswith('M'):
                    amount = float(amount_text[:-1]) * 1_000_000
                elif amount_text.endswith('K'):
                    amount = float(amount_text[:-1]) * 1_000
                else:
                    amount = float(amount_text.replace(",", ""))

                # Validate the converted amount
                if not isinstance(amount, (int, float)):
                    print(f"Invalid amount type for {symbol}: {type(amount)}")
                    continue
                if amount < 0:
                    print(f"Negative amount for {symbol}: {amount}")
                    continue

                holdings_data[symbol] = amount
                processed_symbols.add(symbol)

            except ValueError as e:
                print(f"Error converting amount for {symbol}: {amount_text} - {str(e)}")
                continue
            except Exception as e:
                print(f"Error processing {symbol}: {str(e)}")
                continue

        except Exception as e:
            print(f"Error processing container: {str(e)}")
            continue

    if not holdings_data:
        print("No valid holdings data extracted")
        return None, None

    print(f"Successfully extracted {len(holdings_data)} holdings")
    return holdings_data, total_value

# **📌 Save Data to MySQL**
def save_data_to_mysql(entity_config, holdings_data, total_value):
    """Save extracted data into MySQL with all cryptocurrencies as columns."""
    if not holdings_data:
        print("No holdings data to save")
        return

    connection = connect_to_database()
    if not connection:
        print("MySQL Connection Failed.")
        return

    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"Saving data for date: {today_date}")
    
    try:
        with connection.cursor() as cursor:
            # Convert total_value to float
            if isinstance(total_value, str):
                total_value = total_value.replace("$", "").replace(",", "")
                try:
                    total_value = float(total_value)
                except ValueError:
                    total_value = 0.0

            # Prepare column names and values
            columns = ["date"] + [f"`{key}`" for key in holdings_data.keys()] + ["total_value"]
            values = [today_date] + list(holdings_data.values()) + [total_value]
            
            # Create placeholders for SQL query
            placeholders = ", ".join(["%s"] * len(columns))
            columns_str = ", ".join(columns)
            
            # Prepare DUPLICATE KEY UPDATE part
            update_str = ", ".join(
                f"{col} = VALUES({col})" 
                for col in columns 
                if col != "date"
            )

            # Insert or update query
            query = f"""
                INSERT INTO {entity_config['table']} ({columns_str})
                VALUES ({placeholders})
                ON DUPLICATE KEY UPDATE {update_str}
            """
            
            cursor.execute(query, values)
            connection.commit()
            print("Successfully saved data to database")
            
    except Exception as e:
        print(f"MySQL Save Error: {e}")
    finally:
        connection.close()
        print("Database connection closed")

# **📌 Load Data for Comparison**
def load_data_from_mysql(entity_config):
    connection = connect_to_database()
    if not connection:
        return []

    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {entity_config['table']} ORDER BY date DESC")
            return cursor.fetchall()
    finally:
        connection.close()

# **📌 Calculate Changes**
def format_number(value):
    """Format number to show minimal necessary decimals."""
    value = float(value)
    if value == 0:
        return "0"
    
    # Convert to string with max precision
    str_value = f"{value:.8f}".rstrip('0').rstrip('.')
    
    # If it's a whole number, format with commas
    if '.' not in str_value:
        return f"{int(value):,}"
    
    return f"{float(str_value):,}"

def convert_to_float(value):
    """Convert string values with 'K', 'M', or 'B' into float numbers."""
    if isinstance(value, str):
        value = value.replace(",", "").strip()

        if value.endswith("B"):  # Billions
            return float(value.replace("B", "")) * 1_000_000_000
        elif value.endswith("M"):  # Millions
            return float(value.replace("M", "")) * 1_000_000
        elif value.endswith("K"):  # Thousands
            return float(value.replace("K", "")) * 1_000
        try:
            return float(value)
        except ValueError:
            return 0

    return value

def calculate_changes(new_data, old_data):
    """Calculate daily and monthly asset quantity change, ensuring numeric values."""
    daily_changes = {}
    monthly_changes = {}

    for new in new_data:
        asset_symbol = new["asset_symbol"]
        new_amount = convert_to_float(new["amount"])
        
        # ✅ Get the previous day's entry
        old_entry = next((item for item in old_data if item["asset_symbol"] == asset_symbol), None)
        old_amount = convert_to_float(old_entry["amount"]) if old_entry else 0

        # ✅ Calculate daily change
        daily_changes[asset_symbol] = new_amount - old_amount if old_entry else "No Data"

        # ✅ Calculate monthly change
        total_change = "Shown after 1 month"
        for i in range(1, 31):  # Last 30 days
            past_entry = next((item for item in old_data 
                             if item["asset_symbol"] == asset_symbol 
                             and item["date"] == (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")), None)
            if past_entry:
                total_change = new_amount - convert_to_float(past_entry["amount"])
                break

        monthly_changes[asset_symbol] = total_change

    return daily_changes, monthly_changes

# **📌 Display Data in Table**
def generate_table(entity_config, html_content=None):
    """Generate a report table from MySQL data."""
    all_data = load_data_from_mysql(entity_config)
    if not all_data:
        print("No historical data available.")
        return "No historical data available."

    # Convert data to DataFrame for insights and sort by date (oldest first)
    df = pd.DataFrame(all_data)
    df['date'] = pd.to_datetime(df['date'])  # Ensure date is datetime
    df = df.sort_values('date', ascending=True)  # Explicitly sort oldest to newest
    
    # Get insights data and display assets
    insights, display_assets = get_insight(df)
    
    # Get the two most recent dates
    dates = sorted(set(entry["date"].strftime("%Y-%m-%d") for entry in all_data), reverse=True)
    if not dates:
        return "No data found."
    
    
    latest_date = dates[0]
    previous_date = dates[1] if len(dates) > 1 else None

    # Get the data for each date
    latest_data = next((entry for entry in all_data if entry["date"].strftime("%Y-%m-%d") == latest_date), None)
    previous_data = next((entry for entry in all_data if entry["date"].strftime("%Y-%m-%d") == previous_date), None)

    if not latest_data:
        return "No current data found."

    # Get total value
    total_value = float(latest_data["total_value"]) if latest_data["total_value"] else 0.0

    # Create display list of cryptos
    display_cryptos = []
    
    # First add DEFAULT_ASSETS
    for asset in DEFAULT_ASSETS:
        if asset in latest_data and asset not in display_cryptos:
            display_cryptos.append(asset)
    
    # Add cryptos from insights
    for asset in display_assets:
        if asset not in display_cryptos:
            display_cryptos.append(asset)

    # If we still need more cryptos and we have HTML content, get them from there
    if len(display_cryptos) < 5 and html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        holdings_containers = soup.find_all("div", class_="Portfolio_holdingsContainer__XyaUq")
        
        for container in holdings_containers:
            symbol_span = container.find("span", class_="Portfolio_holdingsSymbol__uOpkQ")
            if symbol_span:
                symbol = symbol_span.get_text(strip=True)
                if symbol not in display_cryptos:
                    display_cryptos.append(symbol)
                    if len(display_cryptos) >= 5:
                        break

    # Create a list of tuples (crypto, current_value) for sorting
    crypto_values = []
    for crypto in display_cryptos:
        if crypto in latest_data and latest_data[crypto]:
            crypto_values.append((crypto, float(latest_data[crypto])))
    
    # Sort by current value in descending order
    crypto_values.sort(key=lambda x: x[1], reverse=True)
    
    # Generate table
    table_output = f"{entity_config['emoji']} *{entity_config['title']}* (Total Portfolio Value: ${total_value:,.2f})\n"
    header = "{:<12} {:<12} {:<12} {:<12}".format("Asset", "Today", "Yesterday", "")  # Empty header for percentage
    table_output += "```\n" + header + "\n" + "-" * 48 + "\n"  # Adjusted line length for new column widths

    # Use sorted crypto list
    for crypto, today in crypto_values:
        # Convert today's value to float
        today = float(today)
        
        # Get yesterday's value and convert to float if exists
        yesterday = float(previous_data[crypto]) if previous_data and previous_data[crypto] is not None else None

        # Format current value
        today_formatted = format_number(today)

        # Calculate and format change and percentage
        if yesterday is not None:  # Check for None specifically
            change = today - yesterday
            if change > 0:
                yesterday_formatted = f"+{format_number(abs(change))}"
                pct_change = ((today - yesterday) / yesterday) * 100
                pct_formatted = f"({pct_change:+.1f}%)"
            elif change < 0:
                yesterday_formatted = f"-{format_number(abs(change))}"
                pct_change = ((today - yesterday) / yesterday) * 100
                pct_formatted = f"({pct_change:+.1f}%)"
            else:
                yesterday_formatted = "0"
                pct_formatted = "(=)"  # Show equals sign for no change
        else:
            yesterday_formatted = "No Data"
            pct_formatted = ""

        table_output += "{:<12} {:<12} {:<12} {:<12}\n".format(
            crypto, today_formatted, yesterday_formatted, pct_formatted
        )

    table_output += "```"
    
    # Add insights below table
    table_output += insights

    return table_output

def get_streaks(df, columns):
    """Find the longest buying/selling streaks."""
    if len(df) < 2:  # Need at least today and yesterday
        return [], []
        
    streaks = {}
    for column in columns:
        if column not in df.columns:
            continue
            
        # Convert column to float type before diff
        df[column] = df[column].astype(float)
        changes = df[column].diff().iloc[1:]  # Skip first NaN from diff()
        
        direction = None
        streak_count = 0
        for change in changes[::-1]:
            if pd.isna(change):  # Skip NaN values
                continue
                
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
                
        if streak_count > 1: 
            streaks[column] = (direction, streak_count)
    
    if not streaks:
        return [], []
    
    # Group assets by direction and streak count
    max_streak = max(streak[1] for streak in streaks.values())
    buying_assets = [asset for asset, (dir, count) in streaks.items() 
                    if count == max_streak and dir == "buying"]
    selling_assets = [asset for asset, (dir, count) in streaks.items() 
                     if count == max_streak and dir == "selling"]
    
    # Create combined message
    message_parts = []
    if selling_assets:
        message_parts.append(f"{', '.join(selling_assets)} selling")
    if buying_assets:
        message_parts.append(f"{', '.join(buying_assets)} buying")
    
    if message_parts:
        messages = [f"Holdings of {' and '.join(message_parts)} for *{max_streak} days straight*"]
        return buying_assets + selling_assets, messages
    
    return [], []

def get_reversal(df, columns):
    """Find buying to selling and selling to buying reversals."""
    if len(df) < 3:  # Need at least 3 days to detect reversal
        return [], []
        
    assets = []
    messages = []
    for column in columns:
        if column not in df.columns:
            continue
        changes = df[column].diff().iloc[1:]
        today_change = changes.iloc[-1]
        
        # Count the streak before the reversal
        streak_count = 0
        prev_direction = None
        for change in changes.iloc[::-1]:
            if change == 0:
                break
            if prev_direction is None:
                prev_direction = "selling" if change < 0 else "buying"
                streak_count = 1
            elif (change < 0 and prev_direction == "selling") or (change > 0 and prev_direction == "buying"):
                streak_count += 1
            else:
                break
                
        # Check if today reversed the streak
        if streak_count >= 1:
            if (today_change > 0 and prev_direction == "selling") or (today_change < 0 and prev_direction == "buying"):
                direction = "buying" if today_change > 0 else "selling"
                
                assets.append(column)
                messages.append(
                    f"Position in {column} shifted to {direction} after {prev_direction} streak of {streak_count} days"
                )
    
    return assets, messages

def get_max_changes(df, columns):
    """Find maximum percentage increases and decreases."""
    if len(df) < 2:  # Need at least today and yesterday
        return [], []
        
    assets = []
    messages = []
    max_increase = (None, -float('inf'))
    max_decrease = (None, float('inf'))
    
    for column in columns:
        if column not in df.columns:
            continue
            
        today_value = df[column].iloc[-1]  # Include today's value
        yesterday_value = df[column].iloc[-2]
        
        if yesterday_value == 0:
            continue
            
        pct_change = ((today_value - yesterday_value) / yesterday_value) * 100
        
        if pct_change > max_increase[1]:
            max_increase = (column, pct_change)
        if pct_change < max_decrease[1]:
            max_decrease = (column, pct_change)
    
    if max_increase[0] and max_increase[1] > 0:
        assets.append(max_increase[0])
        messages.append(
            f"Holdings of {max_increase[0]} saw largest increase (*{max_increase[1]:+.2f}%*)"
        )
        
    if max_decrease[0] and max_decrease[1] < 0:
        assets.append(max_decrease[0])
        messages.append(
            f"Holdings of {max_decrease[0]} saw largest decrease (*{max_decrease[1]:+.2f}%*)"
        )
    
    return assets, messages

def get_insight(df, display_columns=None):
    """Generate insights from the data."""
    insights = []
    display_assets = set()
    
    # Use all columns except 'date', 'USDT', and 'total_value' if no display_columns provided
    if display_columns is None:
        display_columns = [col for col in df.columns if col not in ['date', 'USDT', 'total_value']]
    else:
        display_columns = [col for col in display_columns if col not in ['USDT', 'total_value']]
    
    # Get all insights
    streak_assets, streak_msgs = get_streaks(df, display_columns)
    reversal_assets, reversal_msgs = get_reversal(df, display_columns)
    change_assets, change_msgs = get_max_changes(df, display_columns)
    
    # Add all messages in order
    insights.extend(streak_msgs)
    insights.extend(reversal_msgs)
    insights.extend(change_msgs)
    
    # Collect unique assets for display
    display_assets.update(streak_assets)
    display_assets.update(reversal_assets)
    display_assets.update(change_assets)
    
    # Format insights
    if not insights:
        return "No notable changes detected in asset holdings and trading patterns.", list(display_assets)
    
    return "\n".join(f"*{i+1})* {insight}" for i, insight in enumerate(insights)), list(display_assets)

# **📌 Main Execution**
def get_entity_data(entity_name):
    """Main function to fetch and process entity data."""
    if entity_name not in ENTITIES:
        print(f"Unknown entity: {entity_name}")
        return None
        
    entity_config = ENTITIES[entity_name]
    print(f"\n=== Starting {entity_config['title']} Data Collection ===")
    
    # Update URL in options
    global URL
    URL = entity_config['url']
    
    # Fetch data first
    html_content = fetch_data_with_firefox()
    if not html_content:
        print("Unable to fetch data from website")
        return None
    print("Successfully fetched HTML content")
    
    # Initialize database with the fetched content
    initialize_database(entity_config, html_content)
    print("Database initialized")

    holdings_data, total_value = extract_holdings_and_value(html_content)
    if not holdings_data:
        print("Unable to extract holdings data")
        return None
    print(f"Successfully extracted data for {len(holdings_data)} assets")

    save_data_to_mysql(entity_config, holdings_data, total_value)
    print("Data saving process completed")
    
    try:
        msg = generate_table(entity_config, html_content)
        print("Message generated successfully")
        return msg
    except Exception as e:
        print(f"Error generating table message: {str(e)}")
        return None
    finally:
        # Stop and remove the Docker container
        try:
            client = docker.from_env()
            container_name = "selenium-firefox"
            container = client.containers.get(container_name)
            print(f"Stopping and removing {container_name} container")
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            print(f"Container {container_name} already removed")
        except Exception as e:
            print(f"Error cleaning up container: {e}")

def get_entities():
    """Main function to process all entities."""
    msg = ""
    try:
        for entity_name in ENTITIES.keys():
            entity_msg = get_entity_data(entity_name)
            if entity_msg:
                print(f"\nSuccessfully generated message for {entity_name}:")
                print(entity_msg)
                msg += entity_msg + "\n\n"  # Add newlines between entity messages
            else:
                print(f"\nFailed to generate message for {entity_name}")
        return msg.rstrip()  # Remove trailing newlines
    except Exception as e:
        print(f"\nError in main process: {e}")
        return None

if __name__ == "__main__":
    msg = get_entities()
    if msg:
        print("\nFinal combined message:")
        print(msg)
    else:
        print("\nNo messages generated")
        