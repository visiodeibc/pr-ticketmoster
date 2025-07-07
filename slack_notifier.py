import os
import requests
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
# Set up logging
logger = logging.getLogger('slack_notifier')

# Set your Slack webhook URL
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

def send_slack_notification(ticket_group):
    """
    Send a notification to Slack when a group of similar tickets is found
    
    Args:
        ticket_group: Dictionary containing:
            - issue_type: Common issue description
            - tickets: List of tickets with that issue
    
    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    if not SLACK_WEBHOOK_URL:
        logger.error("SLACK_WEBHOOK_URL environment variable not set")
        
        # For testing without webhook, just log the notification
        ticket_count = len(ticket_group['tickets'])
        issue_type = ticket_group['issue_type']
        logger.info(f"TEST MODE: Would send alert for {ticket_count} tickets with issue: {issue_type}")
        for ticket in ticket_group['tickets']:
            logger.info(f"- Ticket #{ticket['id']}: {ticket['subject']}")
        return True  # Return True for testing
    
    # Format the ticket information
    ticket_count = len(ticket_group['tickets'])
    issue_type = ticket_group['issue_type']
    
    # Create ticket links
    ticket_links = []
    for ticket in ticket_group['tickets']:
        zendesk_url = f"https://amplitude.zendesk.com/agent/tickets/{ticket['id']}"
        ticket_links.append(f"<{zendesk_url}|#{ticket['id']}> - {ticket['subject']}")
    
    ticket_list = "\n".join(ticket_links)
    
    # Format the Slack message
    message = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 Alert: {ticket_count} Similar Support Tickets Detected"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Issue Type:* {issue_type}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Tickets:*\n{ticket_list}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Alert triggered at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View All Tickets"
                        },
                        "url": "https://yourcompany.zendesk.com/agent/search/1",  # Replace with actual search URL
                        "style": "primary"
                    }
                ]
            }
        ]
    }
    
    # Send the notification to Slack
    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            data=json.dumps(message),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("Slack alert sent successfully")
            return True
        else:
            logger.error(f"Slack alert failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Slack notification error: {e}")
        return False 