import os
import requests
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from constants import SLACK_MAX_TEXT_LENGTH, SLACK_MAX_BLOCKS
load_dotenv()
# Set up logging
logger = logging.getLogger('slack_notifier')

# Set your Slack webhook URL
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

def truncate_text(text, max_length=SLACK_MAX_TEXT_LENGTH):
    """Truncate text to fit Slack limits"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def truncate_ticket_list(ticket_links, max_length=SLACK_MAX_TEXT_LENGTH):
    """Truncate ticket list to fit Slack limits"""
    if not ticket_links:
        return "No tickets found"
    
    result = ""
    truncated_count = 0
    
    for i, link in enumerate(ticket_links):
        test_result = result + link + "\n"
        if len(test_result) > max_length - 100:  # Leave room for truncation message
            truncated_count = len(ticket_links) - i
            break
        result = test_result
    
    if truncated_count > 0:
        result += f"\n... and {truncated_count} more tickets"
    
    return result.strip()

def get_ticket_id(ticket):
    """Extract ticket ID from either format (id or ticket_id)"""
    return ticket.get('id') or ticket.get('ticket_id')

def get_ticket_subject(ticket):
    """Extract ticket subject from either format"""
    return ticket.get('subject', 'No subject')

def generate_slack_title(ticket_group, ticket_count):
    """Generate appropriate Slack title based on the notification type"""
    issue_type = ticket_group.get('issue_type', '')
    
    # Check if this is a custom query (starts with "Custom Query:")
    if issue_type.startswith('Custom Query:'):
        return f"📊 Query Results: {ticket_count} Tickets Found"
    else:
        # This is a clustering alert
        return f"🚨 Alert: {ticket_count} Similar Support Tickets Detected"

def send_slack_notification(ticket_group):
    """
    Send a notification to Slack when a group of similar tickets is found
    
    Args:
        ticket_group: Dictionary containing:
            - issue_type: Common issue description or "Custom Query: question"
            - tickets: List of tickets with that issue
            - summary: (optional) Custom summary from OpenAI
            - parsed_data: (optional) Full parsed data from OpenAI
    
    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    if not SLACK_WEBHOOK_URL:
        logger.error("SLACK_WEBHOOK_URL environment variable not set")
        
        # For testing without webhook, just log the notification
        ticket_count = len(ticket_group.get('tickets', []))
        issue_type = ticket_group.get('issue_type', 'Unknown Issue')
        summary = ticket_group.get('summary', '')
        
        title = generate_slack_title(ticket_group, ticket_count)
        logger.info(f"TEST MODE: {title}")
        logger.info(f"Issue: {issue_type}")
        if summary:
            logger.info(f"Summary: {summary}")
        for ticket in ticket_group.get('tickets', []):
            ticket_id = get_ticket_id(ticket)
            subject = get_ticket_subject(ticket)
            logger.info(f"- Ticket #{ticket_id}: {subject}")
        return True  # Return True for testing
    
    # Format the ticket information
    tickets = ticket_group.get('tickets', [])
    ticket_count = len(tickets)
    issue_type = ticket_group.get('issue_type', 'Unknown Issue')
    summary = ticket_group.get('summary', '')
    
    # Generate appropriate title
    title = generate_slack_title(ticket_group, ticket_count)
    
    # Create ticket links
    ticket_links = []
    for ticket in tickets:
        ticket_id = get_ticket_id(ticket)
        subject = get_ticket_subject(ticket)
        if ticket_id:
            zendesk_url = f"https://amplitude.zendesk.com/agent/tickets/{ticket_id}"
            ticket_links.append(f"<{zendesk_url}|#{ticket_id}> - {subject}")
        else:
            ticket_links.append(f"Unknown ID - {subject}")
    
    ticket_list = truncate_ticket_list(ticket_links)
    
    # Use summary if available, otherwise use issue_type
    main_text = summary if summary else issue_type
    
    # For custom queries, clean up the issue_type display
    if issue_type.startswith('Custom Query:'):
        query_text = issue_type.replace('Custom Query: ', '')
        display_text = f"*Query:* {query_text}\n*Result:* {main_text}"
    else:
        display_text = f"*Issue Type:* {main_text}"
    
    # Truncate display text to fit Slack limits
    display_text = truncate_text(display_text)
    
    # Format the Slack message
    message = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": truncate_text(title, 150)  # Headers have stricter limits
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": display_text
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
                        "text": f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
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