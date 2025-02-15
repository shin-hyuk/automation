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

# Base URL for all entities
BASE_URL = "https://intel.arkm.com/explorer/entity/"

# Entity configurations grouped by category
ENTITIES = {
    "ETFs": {
        "blackrock": {
            "url": f"{BASE_URL}blackrock",
            "table": "blackrock_holdings",
            "title": "BlackRock"
        },
        "fidelity": {
            "url": f"{BASE_URL}fidelity-custody",
            "table": "fidelity_holdings",
            "title": "Fidelity"
        },
        "grayscale": {
            "url": f"{BASE_URL}grayscale",
            "table": "grayscale_holdings",
            "title": "Grayscale"
        },
        "ark": {
            "url": f"{BASE_URL}ark-invest",
            "table": "ark_holdings",
            "title": "ARK Invest"
        },
        "bitwise": {
            "url": f"{BASE_URL}bitwise",
            "table": "bitwise_holdings",
            "title": "Bitwise"
        }
    },
    "CEX": {
        "binance": {
            "url": f"{BASE_URL}binance",
            "table": "binance_holdings",
            "title": "Binance"
        },
        "coinbase": {
            "url": f"{BASE_URL}coinbase",
            "table": "coinbase_holdings",
            "title": "Coinbase"
        },
        "bitfinex": {
            "url": f"{BASE_URL}bitfinex",
            "table": "bitfinex_holdings",
            "title": "Bitfinex"
        },
        "kraken": {
            "url": f"{BASE_URL}kraken",
            "table": "kraken_holdings",
            "title": "Kraken"
        },
        "robinhood": {
            "url": f"{BASE_URL}robinhood",
            "table": "robinhood_holdings",
            "title": "Robinhood"
        }
    },
    "Companies": {
        "microstrategy": {
            "url": f"{BASE_URL}microstrategy",
            "table": "microstrategy_holdings",
            "title": "MicroStrategy"
        },
        "worldliberty": {
            "url": f"{BASE_URL}worldlibertyfi",
            "table": "worldliberty_holdings",
            "title": "World Liberty Fi"
        },
        "usg": {
            "url": f"{BASE_URL}usg",
            "table": "usg_holdings",
            "title": "US Government"
        }
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
def create_tables_if_not_exist(entity_config):
    """Create tables for entity if they don't exist."""
    print(f"\nCreating tables for {entity_config['title']}")
    
    # Fetch data to determine table structure
    html_content = fetch_data_with_firefox(entity_config['url'])
    if not html_content:
        print("Unable to fetch data from website")
        return None
    print("Successfully fetched HTML content")
    
    # Initialize database tables
    connection = connect_to_database()
    if not connection:
        return None

    try:
        with connection.cursor() as cursor:
            # Get all possible cryptocurrencies from the webpage
            soup = BeautifulSoup(html_content, "html.parser")
            holdings_containers = soup.find_all("div", class_="Portfolio_holdingsContainer__XyaUq")
            crypto_list = []
            
            for container in holdings_containers:
                symbol_span = container.find("span", class_="Portfolio_holdingsSymbol__uOpkQ")
                if symbol_span:
                    symbol = symbol_span.get_text(strip=True)
                    if symbol not in crypto_list:
                        crypto_list.append(symbol)

            print(f"Found {len(crypto_list)} unique cryptocurrencies")
            
            # Create tables based on number of cryptocurrencies
            if len(crypto_list) <= 200:
                # Single table case
                create_query = f"""
                    CREATE TABLE IF NOT EXISTS {entity_config['table']} (
                        date DATE NOT NULL PRIMARY KEY
                    )
                """
                cursor.execute(create_query)
                connection.commit()
                
                # Add columns for cryptocurrencies
                for symbol in crypto_list:
                    try:
                        cursor.execute(f"""
                            ALTER TABLE {entity_config['table']}
                            ADD COLUMN `{symbol}` DECIMAL(20,4)
                        """)
                        connection.commit()
                    except Exception as e:
                        if "Duplicate column" not in str(e):
                            print(f"Error adding column {symbol}: {e}")
                
            else:
                # Multiple tables case
                num_tables = (len(crypto_list) // 200) + 1
                
                for table_num in range(1, num_tables + 1):
                    table_name = f"{entity_config['table']}{table_num}"
                    start_idx = (table_num - 1) * 200
                    end_idx = min(start_idx + 200, len(crypto_list))
                    table_cryptos = crypto_list[start_idx:end_idx]
                    
                    # Create table
                    create_query = f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            date DATE NOT NULL PRIMARY KEY
                        )
                    """
                    cursor.execute(create_query)
                    connection.commit()
                    
                    # Add columns
                    for symbol in table_cryptos:
                        try:
                            cursor.execute(f"""
                                ALTER TABLE {table_name}
                                ADD COLUMN `{symbol}` DECIMAL(20,4)
                            """)
                            connection.commit()
                        except Exception as e:
                            if "Duplicate column" not in str(e):
                                print(f"Error adding column {symbol}: {e}")
            
            print(f"Tables created successfully for {entity_config['title']}")
            
            # Return the HTML content since we already fetched it
            return html_content
            
    except Exception as e:
        print(f"Error creating tables: {e}")
        return None
    finally:
        connection.close()

# **📌 Fetch Data with Selenium**
def fetch_data_with_firefox(url):
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
        driver.get(url)

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

    # Get total value from header and clean it
    total_value_element = soup.find("span", class_="Header_portfolioValue__AemOW")
    total_value_str = total_value_element.get_text(strip=True) if total_value_element else "0"
    
    # Clean the total value string (remove $ and ,)
    try:
        total_value = float(total_value_str.replace('$', '').replace(',', ''))
    except ValueError as e:
        print(f"Error converting total value {total_value_str}: {e}")
        total_value = 0

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
    """Save data using appropriate table structure."""
    if not holdings_data:
        print("No holdings data to save")
        return

    connection = connect_to_database()
    if not connection:
        return

    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"Saving data for date: {today_date}")
    
    try:
        with connection.cursor() as cursor:
            # Use base table name if not using multiple tables
            if not entity_config.get('use_multiple_tables', False):
                table_name = entity_config['table']
                
                # Prepare column names and values
                columns = ["date"] + list(holdings_data.keys())
                values = [today_date] + list(holdings_data.values())
                
                # Create placeholders and update string
                placeholders = ", ".join(["%s"] * len(columns))
                columns_str = ", ".join(f"`{col}`" for col in columns)
                update_str = ", ".join(
                    f"`{col}` = VALUES(`{col}`)" 
                    for col in columns 
                    if col != "date"
                )

                # Insert or update query
                query = f"""
                    INSERT INTO {table_name} ({columns_str})
                    VALUES ({placeholders})
                    ON DUPLICATE KEY UPDATE {update_str}
                """
                
                cursor.execute(query, values)
                connection.commit()
                print(f"Successfully saved data to {table_name}")
            
            else:
                # Multiple tables approach
                table_count = entity_config.get('table_count', 1)
                for table_num in range(1, table_count + 1):
                    table_name = f"{entity_config['table']}{table_num}"
                    
                    # Get columns for this table
                    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
                    table_columns = {row['Field'] for row in cursor.fetchall()}
                    
                    # Filter holdings data for this table's columns
                    table_holdings = {k: v for k, v in holdings_data.items() 
                                    if k in table_columns}
                    
                    if table_holdings or table_num == 1:  # Always save to first table for total_value
                        # Prepare column names and values
                        columns = ["date"] + list(table_holdings.keys())
                        values = [today_date] + list(table_holdings.values())
                        
                        if table_num == 1:  # Add total_value to first table
                            columns.append("total_value")
                            values.append(total_value)
                        
                        # Create placeholders and update string
                        placeholders = ", ".join(["%s"] * len(columns))
                        columns_str = ", ".join(f"`{col}`" for col in columns)
                        update_str = ", ".join(
                            f"`{col}` = VALUES(`{col}`)" 
                            for col in columns 
                            if col != "date"
                        )

                        # Insert or update query
                        query = f"""
                            INSERT INTO {table_name} ({columns_str})
                            VALUES ({placeholders})
                            ON DUPLICATE KEY UPDATE {update_str}
                        """
                        
                        cursor.execute(query, values)
                        connection.commit()
                        print(f"Successfully saved data to {table_name}")
    
    except Exception as e:
        print(f"MySQL Save Error: {e}")
        print(f"Failed query: {query if 'query' in locals() else 'No query generated'}")
        connection.rollback()
    finally:
        connection.close()

# **📌 Load Data for Comparison**
def load_data_from_mysql(entity_config, table_count=0):
    """Load data using appropriate table structure."""
    if table_count > 0:
        # Multiple tables load logic
        connection = connect_to_database()
        if not connection:
            return []

        try:
            with connection.cursor() as cursor:
                all_data = []
                
                # Load data from first table (contains total_value)
                first_table = f"{entity_config['table']}1"
                cursor.execute(f"SELECT * FROM {first_table} ORDER BY date DESC")
                all_data = cursor.fetchall()
                
                # Load and merge data from additional tables
                for table_num in range(2, table_count + 1):
                    table_name = f"{entity_config['table']}{table_num}"
                    cursor.execute(f"SELECT * FROM {table_name} ORDER BY date DESC")
                    additional_data = cursor.fetchall()
                    
                    # Merge data by date
                    for i, row in enumerate(all_data):
                        if i < len(additional_data):
                            all_data[i].update({k: v for k, v in additional_data[i].items() 
                                              if k not in ['id', 'date']})
                
            return all_data
        finally:
            connection.close()
    else:
        # Original single table load logic
        table_name = entity_config['table']
        connection = connect_to_database()
        if not connection:
            return []

        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM {table_name} ORDER BY date DESC")
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
        # Calculate absolute change for max_increase[0]
        today_value = df[max_increase[0]].iloc[-1]
        yesterday_value = df[max_increase[0]].iloc[-2]
        abs_change = today_value - yesterday_value
        messages.append(
            f"Holdings of {max_increase[0]} saw largest increase {int(abs_change):+} (*{max_increase[1]:+.2f}%*)"
        )
        
    if max_decrease[0] and max_decrease[1] < 0:
        assets.append(max_decrease[0])
        # Calculate absolute change for max_decrease[0] 
        today_value = df[max_decrease[0]].iloc[-1]
        yesterday_value = df[max_decrease[0]].iloc[-2]
        abs_change = today_value - yesterday_value
        messages.append(
            f"Holdings of {max_decrease[0]} saw largest decrease {int(abs_change):+} (*{max_decrease[1]:+.2f}%*)"
        )
    return assets, messages

def get_insight(df, display_columns=None):
    """Generate insights from the data."""
    insights = []
    display_assets = set()
    
    # Use all columns except 'date', USDT and USDC if no display_columns provided
    if display_columns is None:
        display_columns = [col for col in df.columns if col != 'date' and 'USDT' not in col and 'USDC' not in col]
    
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
    
    # Format insights - escape special characters for markdown
    if not insights:
        return None, list(display_assets)
    
    # Escape special characters and format numbers
    formatted_insights = []
    for i, insight in enumerate(insights, 1):
        # Replace markdown formatting with escaped versions
        insight = insight.replace('_', '\\_')
        insight = insight.replace('`', '\\`')
        insight = insight.replace('[', '\\[')
        insight = insight.replace(']', '\\]')
        if len(insights) == 1:
            formatted_insights.append(insight)
        else:
            formatted_insights.append(f"{i}) {insight}")
    
    return formatted_insights, list(display_assets)

# **📌 Main Execution**
def get_entity_data(entity_config):
    """Main function to fetch and process entity data."""
    print(f"\n=== Starting {entity_config['title']} Data Collection ===")
    
    # Check if we already have today's data
    connection = connect_to_database()
    if not connection:
        return None
        
    try:
        with connection.cursor() as cursor:
            today_date = datetime.now().strftime("%Y-%m-%d")
            has_today_data = False
            final_table_count = 0
            
            # First check if base table exists
            try:
                cursor.execute(f"""
                    SELECT COUNT(*) as count 
                    FROM {entity_config['table']} 
                    WHERE date = %s
                """, (today_date,))
                result = cursor.fetchone()

                if result:
                    print(f"  ✓ Found today's data in {entity_config['table']}")
                    has_today_data = True
                else:
                    print(f"  × No data for today in {entity_config['table']}")
            except Exception as e:
                # Base table doesn't exist, continue to check numbered tables
                pass

            # If base table exists, check numbered tables
            table_count = 1
            while True:
                table_pattern = f"{entity_config['table']}{table_count}"
                try:
                    cursor.execute(f"""
                        SELECT COUNT(*) as count 
                        FROM {table_pattern} 
                        WHERE date = %s
                    """, (today_date,))
                    result = cursor.fetchone()

                    if result:
                        print(f"  ✓ Found today's data in {table_pattern}")
                        has_today_data = True
                    else:
                        print(f"  × No data for today in {table_pattern}")
                    
                    table_count += 1
                    final_table_count = table_count - 1
                except Exception as e:
                    # No more tables exist
                    break
            
            if has_today_data:
                return load_data_from_mysql(entity_config, final_table_count)
            
            print(f"\nNo data found for today, proceeding with data collection")
            
            # Create tables if they don't exist
            html_content = create_tables_if_not_exist(entity_config)
            if not html_content:
                return None
                
            # Process and save new data
            holdings_data, total_value = extract_holdings_and_value(html_content)
            if not holdings_data:
                print("Unable to extract holdings data")
                return None
            print(f"Successfully extracted data for {len(holdings_data)} assets")

            save_data_to_mysql(entity_config, holdings_data, total_value)
            print("Data saving process completed")
            
            # Return the newly saved data with the final table count
            return load_data_from_mysql(entity_config, final_table_count)
            
    except Exception as e:
        print(f"Error checking existing data: {e}")
    finally:
        connection.close()

def format_insights_message(all_insights):
    """Format insights into a readable message."""
    message = "🐋 *WHALE TRACKER*\n\n"
    no_changes_by_category = {}
    
    for category, entities in ENTITIES.items():
        has_insights = False
        category_message = f"*{category}*\n"
        temp_message = ""
        category_no_changes = []
        for entity_name, entity_config in entities.items():
            if category not in all_insights or entity_name not in all_insights[category]:
                category_no_changes.append(entity_config['title'])
            else:
                has_insights = True
                changes = all_insights[category][entity_name]
                temp_message += f"│   {entity_config['title']}\n"
                for change in changes:
                    temp_message += f"│   └── {change}\n"
        
        if has_insights:
            message += category_message + temp_message
            if category != list(ENTITIES.keys())[-1]:
                message += "\n"

        if category_no_changes:
            no_changes_by_category[category] = category_no_changes
    
    if no_changes_by_category:
        message += "\n*Entities with No Portfolio Changes*\n"
        for category, entities in no_changes_by_category.items():
            message += f"│   {category}: {', '.join(entities)}\n"
    
    return message

def get_entities():
    """Main function to process all entities and generate insights."""
    all_insights = {}
    
    try:
        # Start Docker container at beginning
        client = docker.from_env()
        container_name = "selenium-firefox"
        
        # Clean up any existing container first
        try:
            container = client.containers.get(container_name)
            print(f"Found existing container {container_name}, removing it...")
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            print(f"No existing container {container_name} found")

        # Start new container
        print(f"Starting new {container_name} container...")
        client.containers.run(
            "selenium/standalone-firefox",
            name=container_name,
            ports={"4444/tcp": 4444},
            detach=True,
        )
        print("Docker container started")
        
        # Process all entities
        for category, entities in ENTITIES.items():
            category_insights = {}
            for entity_name, entity_config in entities.items():
                print(f"\nProcessing {entity_config['title']}...")
                
                entity_data = get_entity_data(entity_config)
                if entity_data and len(entity_data) > 0:
                    try:
                        df = pd.DataFrame(list(entity_data))
                        if not df.empty:
                            df['date'] = pd.to_datetime(df['date'])
                            df = df.sort_values('date', ascending=True)
                            insights, _ = get_insight(df)
                            if insights:
                                category_insights[entity_name] = insights
                    except Exception as e:
                        print(f"Error processing data for {entity_config['title']}: {e}")
                else:
                    print(f"No data available for {entity_config['title']}")
            
            if category_insights:
                all_insights[category] = category_insights
        
        # Format and return the final message
        if all_insights:
            print(format_insights_message(all_insights))
            return format_insights_message(all_insights)
        else:
            return "No insights generated for any entity"
        
    except Exception as e:
        print(f"\nError in main process: {e}")
        return f"Error processing entities: {str(e)}"
    finally:
        # Clean up Docker container at the end
        try:
            container = client.containers.get(container_name)
            print(f"\nStopping and removing {container_name} container...")
            container.stop()
            container.remove()
            print("Container cleanup completed")
        except docker.errors.NotFound:
            print(f"Container {container_name} already removed")
        except Exception as e:
            print(f"Error cleaning up container: {e}")

if __name__ == "__main__":
    msg = get_entities()

    if msg:
        print("\nFinal message:")
        print(msg)
    else:
        print("\nNo insights generated")
        