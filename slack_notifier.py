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
    Send a Slack notification about a group of similar tickets
    
    Args:
        ticket_group: Dictionary containing:
            - issue_type: Type of issue
            - tickets: List of tickets in the group
            - summary: (optional) Summary text for queries
            - parsed_data: (optional) Full parsed data from OpenAI
            - time_window_info: (optional) Time window information for queries
            - is_large_result_set: (optional) Flag for large result sets
    
    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set, skipping Slack notification")
        return False
    
    issue_type = ticket_group.get('issue_type', 'Unknown Issue')
    tickets = ticket_group.get('tickets', [])
    summary = ticket_group.get('summary', '')
    parsed_data = ticket_group.get('parsed_data', {})
    time_window_info = ticket_group.get('time_window_info', {})
    is_large_result_set = ticket_group.get('is_large_result_set', False)
    
    ticket_count = len(tickets)
    
    # Generate title
    title = generate_slack_title(ticket_group, ticket_count)
    
    # Build ticket links - handle both detailed and simplified formats
    ticket_links = []
    
    if is_large_result_set:
        # For large result sets, use ultra-compact format with just ticket numbers
        logger.info(f"Processing large result set with {ticket_count} tickets - using compact format")
        for ticket in tickets:
            ticket_id = ticket.get('ticket_id', 'Unknown')
            if ticket_id and ticket_id != 'Unknown':
                ticket_links.append(f"#{ticket_id}")
            else:
                ticket_links.append(f"#{ticket_id}")
    else:
        # For smaller result sets, use detailed format with full links
        logger.info(f"Processing standard result set with {ticket_count} tickets")
        for ticket in tickets:
            ticket_id = get_ticket_id(ticket)
            subject = get_ticket_subject(ticket)
            org_name = ticket.get('org_name', '')
            org_id = ticket.get('org_id', '')
            assignee = ticket.get('assignee', '')
            
            if ticket_id:
                zendesk_url = f"https://amplitude.zendesk.com/agent/tickets/{ticket_id}"
                
                # Build ticket display with org info and assignee if available
                ticket_display = f"<{zendesk_url}|#{ticket_id}> - {subject}"
                
                # Add organization info
                if org_name and org_id:
                    ticket_display += f" (Org: {org_name} - {org_id})"
                elif org_id:
                    ticket_display += f" (Org ID: {org_id})"
                
                # Add assignee info
                if assignee:
                    ticket_display += f" [Assigned: {assignee}]"
                
                ticket_links.append(ticket_display)
            else:
                ticket_links.append(f"Unknown ID - {subject}")
    
    # For large result sets, use ultra-compact display
    if is_large_result_set:
        # Join with commas for maximum compactness
        ticket_list = ", ".join(ticket_links)
        if len(ticket_list) > SLACK_MAX_TEXT_LENGTH:
            # If still too long, truncate and add count
            logger.warning(f"Slack message too long ({len(ticket_list)} chars > {SLACK_MAX_TEXT_LENGTH} limit)")
            logger.warning(f"Truncating from {len(ticket_links)} tickets to fit Slack limits")
            
            visible_links = []
            current_length = 0
            for link in ticket_links:
                if current_length + len(link) + 2 < SLACK_MAX_TEXT_LENGTH - 50:  # Reserve space for "... and X more"
                    visible_links.append(link)
                    current_length += len(link) + 2
                else:
                    break
            
            remaining_count = len(ticket_links) - len(visible_links)
            ticket_list = ", ".join(visible_links) + f" ... and {remaining_count} more"
            
            logger.warning(f"Displaying {len(visible_links)} tickets in Slack, truncated {remaining_count} tickets")
            logger.info(f"OpenAI found {len(ticket_links)} tickets, Slack displaying {len(visible_links)} tickets")
        else:
            logger.info(f"All {len(ticket_links)} tickets fit within Slack message limits")
    else:
        # For smaller result sets, use detailed format
        ticket_list = truncate_ticket_list(ticket_links)
    
    # Use summary if available, otherwise use issue_type
    main_text = summary if summary else issue_type
    
    # For custom queries, clean up the issue_type display
    if issue_type.startswith('Custom Query:'):
        query_text = issue_type.replace('Custom Query: ', '')
        display_text = f"*Query:* {query_text}\n*Result:* {main_text}"
        
        # Add time window information if available
        if time_window_info:
            time_desc = time_window_info.get('description', 'Unknown time window')
            display_text += f"\n*Time Window:* {time_desc}"
            
            # Add reasoning if available and different from standard
            reasoning = time_window_info.get('reasoning', '')
            if reasoning and not reasoning.startswith('Extracted from query'):
                display_text += f"\n*Note:* {reasoning}"
        
        # Add note for large result sets
        if is_large_result_set:
            display_text += f"\n*Note:* Large result set ({ticket_count} tickets) - showing ticket numbers only"
            display_text += f"\n*Zendesk Link:* <https://amplitude.zendesk.com/agent/tickets|View tickets in Zendesk>"
            
            # Add organization summary if available
            if parsed_data and parsed_data.get('metadata', {}).get('organizations'):
                org_summary = parsed_data['metadata']['organizations']
                org_list = []
                for org_name, org_info in org_summary.items():
                    count = org_info.get('count', 0)
                    org_id = org_info.get('org_id', '')
                    if org_id:
                        org_list.append(f"{org_name} ({org_id}): {count} tickets")
                    else:
                        org_list.append(f"{org_name}: {count} tickets")
                
                if org_list:
                    # Limit to top 5 organizations to avoid message bloat
                    display_orgs = org_list[:5]
                    if len(org_list) > 5:
                        display_orgs.append(f"... and {len(org_list) - 5} more organizations")
                    
                    display_text += f"\n*Organizations:* {', '.join(display_orgs)}"
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
            webhook_url,
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