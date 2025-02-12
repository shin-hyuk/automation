import telegram
from dotenv import load_dotenv
import os

# Load environment variables from root .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Initialize Telegram bot
bot = telegram.Bot(token=BOT_TOKEN)

async def send_message(message, chat_ids=None, parse_mode="Markdown"):
    for chat_id in chat_ids:
        try:
            # Convert chat_id to int if it's a string
            chat_id = int(chat_id)
            await bot.send_message(chat_id=chat_id, text=message, parse_mode=parse_mode)
            print(f"Message sent successfully to chat_id: {chat_id}")
        except Exception as e:
            print(f"Failed to send message to chat_id: {chat_id}. Error: {e}")
