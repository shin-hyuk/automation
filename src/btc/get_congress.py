import time
import random
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
import docker

VOLUME_MIN = 1_000_000    # $1M minimum

# Add this global variable at the top level of the file
MOST_RECENT_TRADE_DATE = None

def fetch_data_with_firefox(url, max_retries=5):
    """Fetch data using existing Selenium WebDriver with retries."""
    for attempt in range(max_retries):
        driver = None
        try:
            driver = webdriver.Remote(
                command_executor="http://localhost:4444/wd/hub",
                options=webdriver.FirefoxOptions()
            )
            print(f"Loading page (attempt {attempt + 1}/{max_retries}): {url}")
            driver.get(url)
            wait_time = random.uniform(10, 20)  # Random wait between 10-20 seconds
            print(f"Waiting {wait_time:.1f} seconds for page load...")
            time.sleep(wait_time)
            
            html_content = driver.page_source
            
            if url == 'https://www.quiverquant.com/congresstrading/':
                soup = BeautifulSoup(html_content, 'html.parser')
                table_outers = soup.find_all("div", class_="table-outer")
                if len(table_outers) >= 2 and table_outers[1].find('table'):
                    return html_content
            else:
                if 'let tradeData = [' in html_content:
                    return html_content
                
            if attempt < max_retries - 1:
                print("Retrying...")
            else:
                print("Max retries reached, giving up.")
                return None
            
        except Exception as e:
            if attempt < max_retries - 1:
                print("Retrying...")
            else:
                print("Max retries reached, giving up.")
                return None
        finally:
            if driver:
                driver.quit()
    
    return None

def parse_trade_volume(volume_str):
    """Convert trade volume string to numeric value"""
    try:
        clean_str = volume_str.replace('$', '').replace(',', '')
        if 'B' in clean_str:
            return float(clean_str.replace('B', '')) * 1_000_000_000
        elif 'M' in clean_str:
            return float(clean_str.replace('M', '')) * 1_000_000
        elif 'K' in clean_str:
            return float(clean_str.replace('K', '')) * 1_000
        else:
            return float(clean_str)
    except:
        return 0

def format_name(raw_name):
    """Clean up politician name by removing whitespace and newlines."""
    return raw_name.strip().replace('\n', '').strip()

def format_link(relative_link):
    """Convert relative link to full Quiver Quant URL."""
    base_url = "https://www.quiverquant.com"
    clean_link = relative_link.replace('../', '')
    formatted_link = clean_link.replace(' ', '%20')
    return f"{base_url}/{formatted_link}"


def get_congress_trades():
    """Get congressional trade insights showing trades from the most recent date."""
    try:
        html_content = fetch_data_with_firefox('https://www.quiverquant.com/congresstrading/')
        if not html_content:
            print("Could not fetch Quiver Quant data")
            return None

        soup = BeautifulSoup(html_content, "html.parser")
        
        # Find all table-outer divs
        table_outers = soup.find_all("div", class_="table-outer")
        if len(table_outers) < 2:
            print("Could not find trades table")
            return None

        # Get the second table
        table = table_outers[1].find('table')
        if not table:
            print("Could not find table within second table-outer")
            return None

        rows = table.find_all('tr')[1:]  # Skip header row
        all_trades = []

        for row in rows:
            try:
                cols = row.find_all('td')
                if not cols or len(cols) < 3:
                    continue

                politician_element = cols[0].find('a')
                if not politician_element:
                    continue

                name_col = cols[0].find('strong')
                if not name_col:
                    continue
                name = name_col.text.strip()
                volume_text = cols[2].find('a').text.strip()
                volume = parse_trade_volume(volume_text)

                trade_info = {
                    'link': format_link(politician_element['href']),
                    'volume': volume,
                    'name': name
                }
                if volume >= VOLUME_MIN:
                    all_trades.append(trade_info)

            except Exception as e:
                continue

        trades_that_day = {'Buy': [], 'Sell': []}
        most_recent_date = None

        for trade_info in all_trades:
            html_content = fetch_data_with_firefox(trade_info['link'])
            if not html_content:
                continue

            soup = BeautifulSoup(html_content, "html.parser")
            trade_table = soup.find("table", {"id": "tradeTable"})
            if not trade_table:
                continue

            trade_rows = trade_table.find_all("tr")[1:]  # Skip header
            
            for row in trade_rows:
                try:
                    tds = row.find_all("td")
                    if not tds or len(tds) < 4:
                        continue
                        
                    # Safely get symbol
                    symbol_div = tds[0].find("div")
                    if not symbol_div:
                        continue
                    symbol_a = symbol_div.find("a", class_="positive")
                    if not symbol_a:
                        continue
                    symbol = symbol_a.text.strip()
                    
                    # Safely get date
                    date_strong = tds[3].find("strong")
                    if not date_strong:
                        continue
                    date = date_strong.text.strip()
                    current_date = datetime.strptime(date, "%b %d, %Y")
                    
                    # Check if this is the most recent trade we've seen
                    if most_recent_date is None or current_date > most_recent_date:
                        print(f"Found newer trade: {trade_info['name']} - {current_date.strftime('%b %d, %Y')}")
                        most_recent_date = current_date
                        trades_that_day = {'Buy': [], 'Sell': []}  # Reset dictionary for new date
                    
                    if most_recent_date and current_date == most_recent_date:
                        # Safely get trade type
                        type_strong = tds[1].find("strong")
                        if not type_strong:
                            continue
                        trade_type = "Buy" if type_strong.text == "Purchase" else "Sell"
                        print(f"Adding trade for {trade_info['name']} - {symbol} ({trade_type}) on {current_date.strftime('%b %d, %Y')}")
                        
                        # Add trade to appropriate list
                        trades_that_day[trade_type].append({
                            'name': trade_info['name'],
                            'symbol': symbol
                        })
                    elif current_date < most_recent_date:
                        print(f"Found older trade: {trade_info['name']} - {current_date.strftime('%b %d, %Y')} (current newest: {most_recent_date.strftime('%b %d, %Y')})")
                        break  # Break the inner loop as remaining trades will be older

                except Exception as e:
                    continue

            time.sleep(random.uniform(1, 2))

        if trades_that_day['Buy'] or trades_that_day['Sell']:
            message = f"*Congress Traders (Most Recent Trade - {most_recent_date.strftime('%b %d')})*\n"
            
            # Process Buy trades
            if trades_that_day['Buy']:
                traders_symbols = {}
                for trade in trades_that_day['Buy']:
                    if trade['name'] not in traders_symbols:
                        traders_symbols[trade['name']] = set()
                    traders_symbols[trade['name']].add(trade['symbol'])
                
                for name, symbols in traders_symbols.items():
                    message += f"│   {name}\n"
                    message += f"│   └── Buy {', '.join(sorted(symbols))}\n"
            
            # Process Sell trades
            if trades_that_day['Sell']:
                traders_symbols = {}
                for trade in trades_that_day['Sell']:
                    if trade['name'] not in traders_symbols:
                        traders_symbols[trade['name']] = set()
                    traders_symbols[trade['name']].add(trade['symbol'])
                
                for name, symbols in traders_symbols.items():
                    message += f"│   {name}\n"
                    message += f"│   └── Sell {', '.join(sorted(symbols))}\n"
            
            return message.rstrip()
        return None

    except Exception as e:
        print(f"Error in get_congress_trades: {e}")
        return None


def format_congress_message(insights):
    """Format congress insights into a readable message."""
    if not insights:
        return "No congress trade insights available"

    message = "*CONGRESS TRACKER* (Last 30days - Most Recent Trade)\n\n"

    for category, traders in insights.items():
        if traders:
            message += f"*{category}*\n"
            # Convert to list and sort by date (in reverse order to get most recent first)
            sorted_traders = sorted(
                traders.items(),
                key=lambda x: datetime.strptime(x[0].split('(')[1].strip(')'), '%b %d'),
                reverse=True
            )
            for trader_name, trades in sorted_traders:
                message += f"│   {trader_name}\n"
                for trade in trades:
                    message += f"│   └── {trade}\n"
            message += "\n"

    return message.rstrip()

def get_congress():
    """Main function to run congress tracker with Docker lifecycle management."""
    try:
        # Start Docker container
        client = docker.from_env()
        container_name = "selenium-firefox"

        # Clean up any existing container
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
        time.sleep(3)  # Give container time to fully start

        # Get insights
        msg = get_congress_trades()
        
        # Return None if no insights or empty message
        if not msg:
            return None

        return msg

    except Exception as e:
        print(f"\nError in main process: {e}")
        return None
    finally:
        # Clean up Docker container
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
    msg = get_congress()
    if msg:
        print("\nFinal message:")
        print(msg)
