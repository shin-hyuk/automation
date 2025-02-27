import os
import json
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import base64

# Load environment variables
load_dotenv()

# Get the Gmail webhook credentials from env
GMAIL_WEBHOOK = os.getenv("GMAIL_WEBHOOK")
if not GMAIL_WEBHOOK:
    raise ValueError("GMAIL_WEBHOOK not found in .env file")

try:
    # Convert JSON string to dictionary
    credentials_data = json.loads(GMAIL_WEBHOOK)
except json.JSONDecodeError as e:
    print("Error parsing GMAIL_WEBHOOK JSON. Make sure it's properly formatted in .env")
    raise

# Define required scopes and paths
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json")

def get_credentials():
    """Get valid credentials, using cached token if available."""
    creds = None

    # Load existing credentials if available
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            print("Found existing credentials")
        except Exception as e:
            print(f"Error loading existing credentials: {e}")
            if os.path.exists(TOKEN_PATH):
                os.remove(TOKEN_PATH)

    # If credentials are invalid or do not exist, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing credentials: {e}")
                creds = None
        
        if not creds:
            print("Getting new credentials")
            flow = InstalledAppFlow.from_client_config(credentials_data, SCOPES)
            creds = flow.run_local_server(port=8080, access_type="offline", prompt="consent")

        # Save credentials for future use
        try:
            with open(TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())
            print("Credentials saved successfully")
        except Exception as e:
            print(f"Error saving credentials: {e}")

    return creds

def get_email_content(service, msg_id):
    """Get the decoded email content"""
    try:
        message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        payload = message.get('payload', {})
        
        # Try to get plain text content
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8')
        elif 'body' in payload and 'data' in payload['body']:
            data = payload['body']['data']
            return base64.urlsafe_b64decode(data).decode('utf-8')
        
        return "No plain text content available"
    except Exception as e:
        return f"Error getting content: {str(e)}"

def parse_email_data(service, msg_data):
    """Extract content from TradingView alerts, returns content string or None"""
    headers = msg_data.get('payload', {}).get('headers', [])
    
    from_address = ""
    subject = ""
    
    # Extract specific headers
    for header in headers:
        name = header.get('name', '').lower()
        if name == 'from':
            from_address = header.get('value', '')
        elif name == 'subject':
            subject = header.get('value', '')
    
    # Only process TradingView alerts
    if "TradingView" in from_address and "Alert:" in subject:
        content = get_email_content(service, msg_data['id'])
        if isinstance(content, dict) and 'decoded' in content:
            return content['decoded']
        return content
    
    return None

def get_alerts():
    try:
        # Get valid credentials
        creds = get_credentials()
        if not creds:
            print("Failed to obtain valid credentials")
            return ""

        # Build Gmail API service
        service = build('gmail', 'v1', credentials=creds)

        # Calculate timestamp for 4 hours ago
        four_hours_ago = int((datetime.now() - timedelta(hours=4)).timestamp())
        
        # Create Gmail query for emails from past 4 hours
        query = f"in:inbox after:{four_hours_ago}"

        # Get recent emails
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])

        if not messages:
            return ""
        
        # Process each email
        all_alerts = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            content = parse_email_data(service, msg_data)
            if content:  # Only append if it's a TradingView alert
                all_alerts.append(content)

        # Combine all alerts with newlines between them
        if all_alerts:
            return "📢 *TradingView Alert*\n\n" + "\n".join(all_alerts)
        return ""

    except Exception as e:
        print(f"Error reading Gmail: {str(e)}")
        return ""

if __name__ == "__main__":
    alerts = get_alerts()
    print(alerts)
