import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
import requests
from bs4 import BeautifulSoup
import re
import openai
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import os
from utils import send_message

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TRADE_CHAT_IDS = os.getenv("TRADE_CHAT_IDS", "").split(",")

# Initialize OpenAI client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

def chat_with_gpt(prompt):
    """Send a prompt to ChatGPT and get a response."""
    completion = client.chat.completions.create(
        model="gpt-4",  # Latest model
        messages=[{"role": "user", "content": prompt}]
    )
    return completion.choices[0].message.content

def extract_date_from_url(url):
    """Extract date from news URL."""
    date_pattern = r'/(\d{2}-\d{2}-\d{4})-'
    match = re.search(date_pattern, url)
    return match.group(1) if match else None

def is_today(date_str):
    """Check if the given date string matches today's date."""
    if not date_str:
        return False
    try:
        news_date = datetime.strptime(date_str, '%m-%d-%Y')
        today = datetime.now()
        return (news_date.day == today.day and 
                news_date.month == today.month and 
                news_date.year == today.year)
    except ValueError:
        return False

def format_single_news(news_item):
    """Format a single news item using ChatGPT."""
    
    prompt = """Please format this news item in a very concise bullet-point style with emojis and hashtags. 
    Follow this format:
    🟡 *[Title]*
     • [Key Point 1 - be very concise, focus on numbers and facts]
     • [Key Point 2 - be very concise, focus on numbers and facts]
    #[Relevant Hashtag1] #[Hashtag2] #[Hashtag3]

    Rules:
    1. Use 🟡 for neutral/mixed news, 🔴 for negative news, and 🟢 for positive news
    2. Make bullet points extremely concise (max 8-10 words)
    3. Focus on key numbers, dates, and facts
    4. Remove unnecessary words and context
    5. Title must be enclosed with asterisks (*) for Telegram formatting
    6. Use 2-3 relevant hashtags
    
    Example format:
    🟡 *U.S. Crypto Tax Reporting Starts 2025*
     • Third-party reporting begins 2025
     • P2P transactions reported from 2027
    #USRegulation #Crypto #IRS

    Here is the news item to format:

    Title: {title}
    Content: {content}
    """.format(title=news_item['title'], content=news_item['content'])

    try:
        formatted_news = chat_with_gpt(prompt)
        
        if formatted_news:
            # Split into lines and process each line
            lines = [line.strip() for line in formatted_news.split('\n') if line.strip()]
            processed_lines = []
            
            for line in lines:
                # If it's a bullet point, ensure consistent format
                if line.startswith('•'):
                    line = ' • ' + line[1:].strip()
                processed_lines.append(line)
            
            # Add star emoji for breaking news if needed
            if news_item['breaking'] and processed_lines[0].startswith(('🟡', '🔴', '🟢')):
                processed_lines[0] = processed_lines[0][:2] + '⭐️' + processed_lines[0][2:]
            
            # Join with single newlines
            formatted_news = '\n'.join(processed_lines)
            
        return formatted_news
        
    except Exception as e:
        print(f"Error in GPT formatting: {e}")
        return None

def format_news_with_gpt(news_list):
    """Format all news items using ChatGPT."""
    formatted_items = []
    
    # Add title with today's date
    today = datetime.now().strftime('%d-%m-%Y')
    title = f"📰 *ETH News Daily ({today})*\n\n"
    
    for news_item in news_list:
        formatted = format_single_news(news_item)
        if formatted:
            formatted_items.append(formatted)
    
    # Combine title with formatted news items
    if formatted_items:
        return title + "\n\n".join(formatted_items)
    return None

def fetch_ethereum_news():
    """Fetch and parse Ethereum news from Binance."""
    
    url = "https://www.binance.com/en/square/news/ethereum%20news"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        news_containers = soup.find_all('div', class_='css-vurnku')
        today_news = []
        
        for container in news_containers:
            news_link = container.find('a', style='display:block;margin-bottom:8px')
            if not news_link:
                continue
                
            title_element = news_link.find('h3')
            content_element = news_link.find('div', class_='css-10lrpzu')
            
            if title_element and content_element:
                href = news_link.get('href', '')
                date = extract_date_from_url(href)
                
                # Only include news from today
                if date and is_today(date):
                    is_breaking = 'css-ifogq4' in title_element.get('class', [])
                    news_item = {
                        'title': title_element.text.strip(),
                        'content': content_element.text.strip(),
                        'date': date,
                        'breaking': is_breaking
                    }
                    today_news.append(news_item)
        
        return today_news

    except requests.RequestException as e:
        print(f"Error fetching news: {e}")
        return []

async def get_news():
    # Fetch the news
    news_list = fetch_ethereum_news()
    
    if news_list:
        # Format news with GPT
        formatted_news = format_news_with_gpt(news_list)
        
        if formatted_news:
            print("\nFormatted News:\n")
            print(formatted_news)
            
            # Send to Telegram with TRADE_CHAT_IDS
            await send_message(formatted_news, chat_ids=TRADE_CHAT_IDS)
    else:
        print("No news found or error occurred while fetching news.")

if __name__ == "__main__":
    asyncio.run(get_news()) 