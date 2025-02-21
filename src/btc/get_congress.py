import time
import random
from bs4 import BeautifulSoup
import docker
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime

# Constants for trade volume categories
HIGH_VOLUME_MIN = 10_000_000  # $10M minimum
MED_VOLUME_MIN = 1_000_000    # $1M minimum

# **📌 Fetch Data with Selenium**
def fetch_data_with_firefox(url):
    """Fetch data using existing Selenium WebDriver."""
    driver = None
    try:
        driver = webdriver.Remote(
            command_executor="http://localhost:4444/wd/hub",
            options=webdriver.FirefoxOptions()
        )
        print(f"Loading page: {url}")
        driver.get(url)
        time.sleep(20)  # Give page time to load
        return driver.page_source
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None
    finally:
        if driver:
            driver.quit()
            
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
    """Get congressional trade insights for two volume categories."""
    try:
        html_content = fetch_data_with_firefox('https://www.quiverquant.com/congresstrading/')
        if not html_content:
            print("Could not fetch Quiver Quant data")
            return None
            
        soup = BeautifulSoup(html_content, "html.parser")
        congress_insights = {
            "High Volume ($10M+)": {},
            "Medium Volume ($1M-$10M)": {}
        }
        
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
        high_volume_trades = []
        med_volume_trades = []
        
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
                
                if volume >= HIGH_VOLUME_MIN:
                    high_volume_trades.append(trade_info)
                elif volume >= MED_VOLUME_MIN:
                    med_volume_trades.append(trade_info)

            except Exception as e:
                print(f"Error processing row: {e}")
                continue
        
        # Sort trades by volume
        high_volume_trades.sort(key=lambda x: x['volume'], reverse=True)
        med_volume_trades.sort(key=lambda x: x['volume'], reverse=True)
        
        # Process trades for both categories
        for category, trades, category_name in [
            (congress_insights["High Volume ($10M+)"], high_volume_trades, "high"),
            (congress_insights["Medium Volume ($1M-$10M)"], med_volume_trades, "medium")
        ]:
            for trade_info in trades:
                html_content = fetch_data_with_firefox(trade_info['link'])
                if not html_content:
                    continue
                    
                soup = BeautifulSoup(html_content, "html.parser")
                trade_table = soup.find("table", {"id": "tradeTable"})
                if not trade_table:
                    continue
                    
                trade_rows = trade_table.find_all("tr")[1:]  # Skip header
                
                recent_date = None
                recent_date_display = None
                trader_trades = {'Buy': [], 'Sell': []}
                
                for row in trade_rows:
                    tds = row.find_all("td")
                    try:
                        symbol = tds[0].find("div").find("a", class_="positive").text
                        date = tds[3].find("strong").text.strip()
                        current_date = datetime.strptime(date, "%b %d, %Y")
                        
                        if recent_date is None:
                            recent_date = current_date
                            recent_date_display = date.split(',')[0].strip()  # Store display format
                            days_old = (datetime.now() - recent_date).days
                    
                            if days_old > 30:
                                print(f"Skipping {trade_info['name']}, most recent trade is {days_old} days old")
                                break
                            else:
                                print(f"{trade_info['name']} - {symbol}: {date} ({days_old} days old)")

                        elif current_date < recent_date:
                            print(f"Breaking on {current_date} < {recent_date.strftime('%b %d, %Y')}")
                            break
                        
                        trade_type = "Buy" if tds[1].find("strong").text == "Purchase" else "Sell"
                        trader_trades[trade_type].append(symbol)
                        
                    except Exception as e:
                        print(f"Error processing trade row: {e}")
                
                if trader_trades['Buy'] or trader_trades['Sell']:
                    trader_insights = []
                    if trader_trades['Buy']:
                        trader_insights.append(f"Buy {', '.join(sorted(set(trader_trades['Buy'])))}")
                    if trader_trades['Sell']:
                        trader_insights.append(f"Sell {', '.join(sorted(set(trader_trades['Sell'])))}")
                    
                    name_with_date = f"{trade_info['name']} ({recent_date_display})"  # Use display format
                    category[name_with_date] = trader_insights
                
                time.sleep(random.uniform(1, 2))
        
        return congress_insights
            
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
        insights = get_congress_trades()
        
        # Format and return the final message
        if insights:
            return format_congress_message(insights)
        else:
            return "No insights generated"
            
    except Exception as e:
        print(f"\nError in main process: {e}")
        return f"Error processing congress trades: {str(e)}"
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
    else:
        print("\nNo insights generated") 