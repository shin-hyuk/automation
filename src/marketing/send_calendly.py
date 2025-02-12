import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
import re
import asyncio
from dotenv import load_dotenv
import os
from utils import send_message

# Load environment variables
load_dotenv()
MARKETING_CHAT_IDS = os.getenv("MARKETING_CHAT_IDS", "").split(",")

def clean_text(text):
    """Removes extra spaces and unnecessary characters."""
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'<https?://\S+>', '', text)  # Remove URLs
    return text

def event_canceled(content):
    patterns = {
        "Event Type": r"Hi (.+?),",
        "Date/Time": r"Event Date/Time:\s*\n*(.+?)\n", 
        "Invitee": r"Invitee:\s*\n*(.+?)\n",
        "Invitee Email": r"Invitee Email:\s*\n*([^\[\s]+?)(?:\s|\[|$)",
        "Canceled": r"Canceled by:\s*\n*(.+?)\n",
    }

    extracted_data = {key: re.search(pattern, content, re.DOTALL) for key, pattern in patterns.items()}
    print(content)
    print(extracted_data)
    formatted_details = {key: clean_text(match.group(1)) if match else "N/A" for key, match in extracted_data.items()}

    # Construct a clean Telegram-friendly message
    msg = (
        f"🚫 *Event Canceled (Calendly)*\n\n"
        f"Event Type: {formatted_details['Event Type']}\n"
        f"Date/Time: {formatted_details['Date/Time']}\n"
        f"Invitee: {formatted_details['Invitee']}\n"
        f"Email: {formatted_details['Invitee Email']}\n"
        f"Canceled by: {formatted_details['Canceled']}\n"
    )
    return msg


def event_new(content):
    patterns = {
        "Event Type": r"Hi (.+?),",
        "Date/Time": r"Event Date/Time:\s*\n*(.+?)\n", 
        "Invitee": r"Invitee:\s*\n*(.+?)\n",
        "Invitee Email": r"Invitee Email:\s*\n*([^\[\s]+?)(?:\s|\[|$)",
        "Are you a": r"Are you a\s*\n*(.+?)\n",
        "Link": r"\[(https://calendly\.com/events/[^\]]+)\]",
        "Where are you located?": r"Where are you located\?\s*\n*(.+?)\n",
        "Primary Reason": r"What is the primary reason for this meeting\?.*?\n\n(.+?)\n",
        "Industry": r"Which industry or type of business are you involved in\?.*?\n\n(.+?)\n",
        "Existing Trusts": r"Do you have any existing trusts or asset management structures in place\?\s*\n*(.+?)\n",
        "Asset Value": r"What is your approximate asset value \(USD\)\?\s*\n*(.+?)\n",
        "Enquiry Details": r"Details of your enquiry:\s*\n*(.+?)\n"
    }
    
    extracted_data = {key: re.search(pattern, content, re.DOTALL) for key, pattern in patterns.items()}
    print(content)
    formatted_details = {key: clean_text(match.group(1)) if match else "N/A" for key, match in extracted_data.items()}
    print(formatted_details)

    # Construct a clean Telegram-friendly message
    msg = (
        f"📅 *New Event Scheduled (Calendly)*\n\n"
        f"*Event Details*\n"
        f"Event Type: {formatted_details['Event Type']}\n"
        f"Date/Time: {formatted_details['Date/Time']}\n"
        f"Reason for Meeting: {formatted_details['Primary Reason']}\n"
        f"Enquiry Details: {formatted_details['Enquiry Details']}\n"
        f"Link: [{formatted_details['Link']}]({formatted_details['Link']})\n"
        f"\n*Invitee Information*\n"
        f"Name: {formatted_details['Invitee']}\n"
        f"Email: {formatted_details['Invitee Email']}\n"
        f"Location: {formatted_details['Where are you located?']}\n"
        f"Industry: {formatted_details['Industry']}\n"
        f"Existing Trusts: {formatted_details['Existing Trusts']}\n"
        f"Status: {formatted_details['Are you a']}\n"
        f"Asset Value: {formatted_details['Asset Value']}\n"
    )
    return msg


def process_email(input_string):
    #{{ $json.from.value[0].address }}|||{{ $json.headers.subject }}|||{{ $json.text }}
    parts = input_string.split("|||")
    sender = parts[0].strip()
    subject = parts[1].strip()
    content = parts[2].strip()
    
    if len(parts) != 3:
        return None

    if "calendly-admin@utgl.io" not in sender:
        print("Not from Calendly.")
        return None

    if "New Event" in subject:
        return event_new(content)
    elif "Canceled" in subject:
        return event_canceled(content)
    else:
        return None


async def send_calendly():
    if len(sys.argv) < 2:
        print("Usage: python script.py 'From:<email> Subject:<text> Content:<text>'")
        return

    input_text = " ".join(sys.argv[1:])  # Keep the entire input as a single string
    message = process_email(input_text)
    
    if message:
        await send_message(message, chat_ids=MARKETING_CHAT_IDS)


if __name__ == "__main__":
    asyncio.run(send_calendly())