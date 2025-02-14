import time
import random
import docker
import pymysql
import pymysql.cursors
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# URLs for different entities
URLS = {
    #ETFs/ETPs
    'BlackRock': 'https://intel.arkm.com/explorer/entity/blackrock',
    'Fidelity': 'https://intel.arkm.com/explorer/entity/fidelity-custody',
    'Grayscale': 'https://intel.arkm.com/explorer/entity/grayscale',
    'ARK Invest': 'https://intel.arkm.com/explorer/entity/ark-invest',
    'Bitwise': 'https://intel.arkm.com/explorer/entity/bitwise',
    
    #CEXs
    'Binance': 'https://intel.arkm.com/explorer/entity/binance',
    'Coinbase': 'https://intel.arkm.com/explorer/entity/coinbase',
    'Bitfinex': 'https://intel.arkm.com/explorer/entity/bitfinex',
    'Kraken': 'https://intel.arkm.com/explorer/entity/kraken',
    'Robinhood': 'https://intel.arkm.com/explorer/entity/robinhood',

    #Public Company 
    'MicroStrategy': 'https://intel.arkm.com/explorer/entity/microstrategy',
    'WorldLiberty': 'https://intel.arkm.com/explorer/entity/worldlibertyfi',
    'USGovernment': 'https://intel.arkm.com/explorer/entity/usg'
}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
]

def connect_to_database():
    """Connect to MySQL database."""
    try:
        connection = pymysql.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection
    except Exception as e:
        print(f"Database Connection Error: {e}")
        return None

def initialize_database():
    """Initialize database with table for BTC holdings."""
    connection = connect_to_database()
    if not connection:
        return

    try:
        with connection.cursor() as cursor:
            # Create base table with date column
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS btc_holdings (
                    date DATE PRIMARY KEY
                )
            """)
            
            # Get existing columns
            cursor.execute("SHOW COLUMNS FROM btc_holdings")
            existing_columns = {row['Field'] for row in cursor.fetchall()}
            
            # Add columns for each entity if they don't exist
            for entity in URLS.keys():
                column_name = entity.replace(' ', '_')
                if column_name not in existing_columns:
                    try:
                        cursor.execute(f"""
                            ALTER TABLE btc_holdings 
                            ADD COLUMN `{column_name}` DECIMAL(20,8)
                        """)
                    except Exception as e:
                        print(f"Error adding column {column_name}: {e}")
            
            connection.commit()
            print("Table btc_holdings is ready")
            
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        connection.close()

def fetch_data_with_firefox(url):
    """Fetch data using Selenium in Docker container."""
    driver = None

    try:
        options = webdriver.FirefoxOptions()
        options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
        options.add_argument("--headless")
        
        driver = webdriver.Remote(
            command_executor="http://localhost:4444/wd/hub",
            options=options
        )

        print(f"Launching Firefox Browser for {url}...")
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

def extract_btc_holdings(html_content):
    """Extract BTC holdings from HTML content."""
    if not html_content:
        return None

    try:
        soup = BeautifulSoup(html_content, "html.parser")
        holdings_containers = soup.find_all("div", class_="Portfolio_holdingsContainer__XyaUq")
        
        for container in holdings_containers:
            symbol_span = container.find("span", class_="Portfolio_holdingsSymbol__uOpkQ")
            if symbol_span and symbol_span.get_text(strip=True) == "BTC":
                # Get amount (first span in container)
                amount_span = container.find("span")
                if amount_span:
                    amount_text = amount_span.get_text(strip=True)
                    
                    # Convert B/M/K values to full numbers
                    try:
                        if amount_text.endswith('B'):
                            amount = float(amount_text[:-1]) * 1_000_000_000
                        elif amount_text.endswith('M'):
                            amount = float(amount_text[:-1]) * 1_000_000
                        elif amount_text.endswith('K'):
                            amount = float(amount_text[:-1]) * 1_000
                        else:
                            amount = float(amount_text.replace(",", ""))

                        # Validate the converted amount
                        if not isinstance(amount, (int, float)):
                            print(f"Invalid amount type: {type(amount)}")
                            continue
                        if amount < 0:
                            print(f"Negative amount: {amount}")
                            continue

                        return amount

                    except ValueError as e:
                        print(f"Error converting amount: {amount_text} - {str(e)}")
                        continue
                    except Exception as e:
                        print(f"Error processing amount: {str(e)}")
                        continue
                        
        return 0  # Return 0 if BTC not found
    except Exception as e:
        print(f"Extraction Error: {e}")
        return None

def save_data_to_mysql(entity, btc_amount):
    """Save extracted BTC data into MySQL."""
    if btc_amount is None:
        print(f"No BTC data to save for {entity}")
        return

    connection = connect_to_database()
    if not connection:
        return

    try:
        with connection.cursor() as cursor:
            today = datetime.now().date()
            column_name = entity.replace(' ', '_')
            
            # First try to insert the date if it doesn't exist
            cursor.execute("""
                INSERT IGNORE INTO btc_holdings (date)
                VALUES (%s)
            """, (today,))
            
            # Then update the entity's column for today
            cursor.execute(f"""
                UPDATE btc_holdings 
                SET `{column_name}` = %s
                WHERE date = %s
            """, (btc_amount, today))
            
            connection.commit()
            print(f"Successfully saved data for {entity}")
            
    except Exception as e:
        print(f"MySQL Save Error: {e}")
    finally:
        connection.close()

def load_data_from_mysql():
    """Load data from MySQL database."""
    connection = connect_to_database()
    if not connection:
        return None

    try:
        with connection.cursor() as cursor:
            # Get all data ordered by date
            cursor.execute("""
                SELECT *
                FROM btc_holdings
                ORDER BY date DESC
            """)
            return cursor.fetchall()
    except Exception as e:
        print(f"Error loading data: {e}")
        return None
    finally:
        connection.close()

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

def generate_table():
    """Generate a report table from MySQL data."""
    all_data = load_data_from_mysql()
    if not all_data:
        print("No historical data available.")
        return "No historical data available."

    # Convert to DataFrame for insights and sort by date (oldest first)
    df = pd.DataFrame(all_data)
    df['date'] = pd.to_datetime(df['date'])  # Ensure date is datetime
    df = df.sort_values('date')  # Sort by date ascending
    
    # Get the two most recent dates
    dates = sorted(set(entry["date"] for entry in all_data), reverse=True)
    if not dates:
        return "No data found."
    
    latest_date = dates[0]
    previous_date = dates[1] if len(dates) > 1 else None

    # Get the data for each date
    latest_data = next((entry for entry in all_data if entry["date"] == latest_date), None)
    previous_data = next((entry for entry in all_data if entry["date"] == previous_date), None)

    if not latest_data:
        return "No current data found."

    # Define categories
    categories = {
        "🌍 *ETFs/ETPs*": ["BlackRock", "Fidelity", "Grayscale", "ARK_Invest", "Bitwise"],
        "💱 *CEXs*": ["Binance", "Coinbase", "Bitfinex", "Kraken", "Robinhood"],
        "🏢 *Public Companies*": ["MicroStrategy", "WorldLiberty", "USGovernment"]
    }

    # Initialize output
    table_output = ""

    # Generate table for each category
    for i, (category_name, category_entities) in enumerate(categories.items()):
        # Get insights for this category
        insights, _ = get_category_insight(df, category_entities)
        
        # Sort entities in this category by current holdings
        sorted_entities = sorted(
            [(entity, float(latest_data[entity] or 0)) for entity in category_entities],
            key=lambda x: x[1],
            reverse=True
        )

        # Generate category table
        table_output += f"{category_name}\n"
        header = "{:<15} {:<12} {:<12} {:<12}".format("Entity", "Today", "Yesterday", "")
        table_output += "```\n" + header + "\n" + "-" * 51 + "\n"

        for entity, today in sorted_entities:
            if today is None:
                continue

            # Get yesterday's value
            yesterday = float(previous_data[entity]) if previous_data and previous_data[entity] is not None else None

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

            table_output += "{:<15} {:<12} {:<12} {:<12}\n".format(
                entity.replace('_', ' '), today_formatted, yesterday_formatted, pct_formatted
            )

        table_output += "```"
        
        # Add insights or default message
        if insights.strip() == "":
            table_output += "No notable changes detected in asset holdings and trading patterns.\n"
        else:
            table_output += insights
        
        # Add extra newlines only if it's not the last table
        if i < len(categories) - 1:
            table_output += "\n"
        else:
            table_output += ""
    
    # Add debug prints
    print("\n=== Debug: Generated Message ===")
    print("Message length:", len(table_output))
    print("Message content:")
    print(table_output)
    print("=== End Debug ===\n")
    
    return table_output

def check_entity_data_exists(entity, date):
    """Check if data exists for entity on given date."""
    connection = connect_to_database()
    if not connection:
        return False

    try:
        with connection.cursor() as cursor:
            column_name = entity.replace(' ', '_')
            cursor.execute(f"""
                SELECT `{column_name}`
                FROM btc_holdings
                WHERE date = %s AND `{column_name}` IS NOT NULL
            """, (date,))
            result = cursor.fetchone()
            return result is not None
    except Exception as e:
        print(f"Error checking data existence: {e}")
        return False
    finally:
        connection.close()

def get_streaks(df, category_entities):
    """Find the longest buying/selling streaks."""
    streaks = {}
    for entity in category_entities:
        if entity not in df.columns:
            continue
        changes = df[entity].diff().iloc[1:]
        direction = None
        streak_count = 0
        for change in changes.iloc[::-1]:  # Reverse order, excluding today
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
                
        if streak_count > 1:  # Only record if streak is longer than 1 day
            streaks[entity] = (direction, streak_count)

    if not streaks:
        return [], []
        
    # Find max streak
    max_streak = max(streaks.values(), key=lambda x: x[1])
    max_streak_assets = [asset for asset, (dir, count) in streaks.items() 
                        if count == max_streak[1] and dir == max_streak[0]]
    
    messages = [f"Holdings of {', '.join(max_streak_assets)} have been {max_streak[0]} for *{max_streak[1]} days straight*"]
    return max_streak_assets, messages

def get_reversal(df, category_entities):
    """Find buying to selling and selling to buying reversals."""
    assets = []
    messages = []
    for entity in category_entities:
        if entity not in df.columns:
            continue
        changes = df[entity].diff().iloc[1:]
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
                
                assets.append(entity)
                messages.append(
                    f"Position in {entity} shifted to {direction} after {prev_direction} streak of {streak_count} days"
                )
    
    return assets, messages

def get_max_changes(df, category_entities):
    """Find maximum percentage increases and decreases."""
    assets = []
    messages = []
    max_increase = (None, -float('inf'))
    max_decrease = (None, float('inf'))
    
    for entity in category_entities:
        if entity not in df.columns:
            continue
            
        today_value = df[entity].iloc[-1]  # Include today's value
        yesterday_value = df[entity].iloc[-2]
        
        if yesterday_value == 0:
            continue
            
        pct_change = ((today_value - yesterday_value) / yesterday_value) * 100
        
        if pct_change > max_increase[1]:
            max_increase = (entity, pct_change)
        if pct_change < max_decrease[1]:
            max_decrease = (entity, pct_change)
    
    if max_increase[0] and max_increase[1] > 0:
        assets.append(max_increase[0])
        messages.append(
            f"Holdings of {max_increase[0].replace('_', ' ')} saw largest increase (*{max_increase[1]:+.2f}%*)"
        )
        
    if max_decrease[0] and max_decrease[1] < 0:
        assets.append(max_decrease[0])
        messages.append(
            f"Holdings of {max_decrease[0].replace('_', ' ')} saw largest decrease (*{max_decrease[1]:+.2f}%*)"
        )
    
    return assets, messages

def get_category_insight(df, category_entities):
    """Generate insights for a specific category."""
    insights = []
    display_assets = set()
    
    # Get all insights for this category
    streak_assets, streak_msgs = get_streaks(df, category_entities)
    reversal_assets, reversal_msgs = get_reversal(df, category_entities)
    change_assets, change_msgs = get_max_changes(df, category_entities)
    
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
        return "", list(display_assets)
    
    return "\n".join(f"*{i+1})* {insight}" for i, insight in enumerate(insights)) + "\n", list(display_assets)

def get_chain():
    """Main function to fetch and process BTC holdings data."""
    print("\n=== Starting BTC Holdings Data Collection ===")
    
    initialize_database()
    print("Database initialized")

    # Start Docker container
    client = docker.from_env()
    container_name = "selenium-firefox"
    image_name = "selenium/standalone-firefox"
    today = datetime.now().date()
    
    try:
        # Clean up any existing container
        try:
            container = client.containers.get(container_name)
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            pass

        # Start new container
        print(f"Starting new {container_name} container...")
        client.containers.run(
            image_name,
            name=container_name,
            ports={"4444/tcp": 4444},
            detach=True,
        )
        time.sleep(5)  # Wait for container to be ready
        
        # Process each entity
        for entity, url in URLS.items():
            # Check if we already have data for this entity today
            if check_entity_data_exists(entity, today):
                print(f"\nSkipping {entity} - data already exists for today")
                continue
                
            print(f"\nProcessing {entity}...")
            html_content = fetch_data_with_firefox(url)
            if html_content:
                btc_amount = extract_btc_holdings(html_content)
                if btc_amount is not None:
                    save_data_to_mysql(entity, btc_amount)
                time.sleep(random.uniform(2, 5))  # Random delay between requests
        
        # Generate final report
        msg = generate_table()
        print("\nReport generated successfully")
        print(msg)
        return msg

    except Exception as e:
        print(f"Error in main process: {e}")
        return None
    finally:
        # Cleanup
        try:
            container = client.containers.get(container_name)
            print(f"\nStopping and removing {container_name} container")
            container.stop()
            container.remove()
        except:
            pass

if __name__ == "__main__":
    result = get_chain()
    if result:
        print("\n=== Final Output ===")
        print(result)
    else:
        print("\n=== Script completed with errors ===")