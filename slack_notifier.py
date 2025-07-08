import os
import requests
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from constants import SLACK_MAX_TEXT_LENGTH, SLACK_MAX_BLOCKS, JIRA_BASE_URL, LARGE_RESULT_THRESHOLD

load_dotenv()

# Configure logging
logger = logging.getLogger('slack_notifier')

def truncate_text(text, max_length=SLACK_MAX_TEXT_LENGTH):
    """Truncate text to fit Slack limits"""
    return text if len(text) <= max_length else text[:max_length-3] + "..."

def truncate_ticket_list(ticket_links, max_length=SLACK_MAX_TEXT_LENGTH):
    """Truncate ticket list to fit Slack limits, handling indented sub-items"""
    if not ticket_links:
        return "No tickets found"
    
    result = ""
    truncated_count = 0
    
    for i, link in enumerate(ticket_links):
        test_result = result + link + "\n"
        if len(test_result) > max_length - 100:
            # Count remaining main tickets (not indented sub-items)
            for item in ticket_links[i:]:
                if not item.startswith('    '):
                    truncated_count += 1
            break
        result = test_result
    
    if truncated_count > 0:
        result += f"\n... and {truncated_count} more tickets"
    
    return result.strip()

def sanitize_text_for_slack(text):
    """Sanitize text for safe inclusion in Slack messages"""
    if not text:
        return text
    # Replace problematic characters that could break JSON or Slack formatting
    sanitized = str(text)
    sanitized = sanitized.replace('"', "'")  # Replace quotes with apostrophes
    sanitized = sanitized.replace('\n', ' ')  # Replace newlines with spaces
    sanitized = sanitized.replace('\r', ' ')  # Replace carriage returns with spaces
    sanitized = sanitized.replace('\t', ' ')  # Replace tabs with spaces
    return sanitized

def get_ticket_data(ticket):
    """Extract common ticket data fields with sanitization for Slack"""
    return {
        'id': ticket.get('id') or ticket.get('ticket_id'),
        'subject': sanitize_text_for_slack(ticket.get('subject', 'No subject')),
        'org_name': sanitize_text_for_slack(ticket.get('org_name', '')),
        'org_id': ticket.get('org_id', '') or ticket.get('numeric_org_id', ''),
        'assignee': sanitize_text_for_slack(ticket.get('assignee', '')),
        'jira_id': ticket.get('jira_id', ''),
        'jira_ticket_id': ticket.get('jira_ticket_id', ''),
        'discourse_link': ticket.get('link_to_discourse', '')
    }

def get_group_ticket_count(group):
    """Get ticket count for a group using multiple fallback methods"""
    # Try count field from OpenAI first
    if group.get('count', 0):
        return group['count']
    
    # Fallback to counting arrays
    tickets_count = len(group.get('tickets', []))
    ticket_ids_count = len(group.get('ticket_ids', []))
    return tickets_count if tickets_count > 0 else ticket_ids_count

def build_jira_link(ticket_data, indent="        "):
    """Build JIRA link with proper formatting"""
    jira_id = ticket_data['jira_id']
    jira_ticket_id = ticket_data['jira_ticket_id']
    
    if not (jira_id or jira_ticket_id):
        return None
    
    # Determine clickable JIRA ID
    clickable_jira_id = None
    if jira_ticket_id and jira_ticket_id.strip():
        clickable_jira_id = jira_ticket_id.strip()
    elif jira_id and jira_id.strip():
        jira_id_cleaned = jira_id.strip()
        if '-' in jira_id_cleaned and any(c.isalpha() for c in jira_id_cleaned):
            clickable_jira_id = jira_id_cleaned
    
    if clickable_jira_id:
        jira_url = f"{JIRA_BASE_URL}/{clickable_jira_id}"
        return f"{indent}📋 JIRA: <{jira_url}|{clickable_jira_id}>"
    elif jira_id and jira_id.strip():
        return f"{indent}📋 JIRA ID: {jira_id.strip()}"
    
    return None

def build_discourse_link(ticket_data, indent="        "):
    """Build Discourse link with proper formatting"""
    discourse_link = ticket_data['discourse_link']
    
    if not discourse_link or not discourse_link.strip():
        return None
    
    discourse_link = discourse_link.strip()
    if discourse_link.startswith('http'):
        return f"{indent}💬 Discourse: <{discourse_link}|View Discussion>"
    else:
        return f"{indent}💬 Discourse: {discourse_link}"

def build_ticket_display(ticket, indent="    "):
    """Build detailed ticket display with links"""
    ticket_data = get_ticket_data(ticket)
    ticket_id = ticket_data['id']
    
    if not ticket_id:
        return f"{indent}• #{ticket_id or 'Unknown'} - {ticket_data['subject']}"
    
    zendesk_url = f"https://amplitude.zendesk.com/agent/tickets/{ticket_id}"
    display = f"{indent}• <{zendesk_url}|#{ticket_id}> - {ticket_data['subject']}"
    
    # Add organization info
    if ticket_data['org_name'] and ticket_data['org_id']:
        display += f" (Org: {ticket_data['org_name']} - {ticket_data['org_id']})"
    elif ticket_data['org_id']:
        display += f" (Org ID: {ticket_data['org_id']})"
    
    # Add assignee info
    if ticket_data['assignee']:
        display += f" [Assigned: {ticket_data['assignee']}]"
    
    displays = [display]
    
    # Add JIRA and Discourse links
    deeper_indent = "        " if indent == "    " else "            "
    
    jira_link = build_jira_link(ticket_data, deeper_indent)
    if jira_link:
        displays.append(jira_link)
    
    discourse_link = build_discourse_link(ticket_data, deeper_indent)
    if discourse_link:
        displays.append(discourse_link)
    
    return displays

def generate_slack_title(ticket_group, ticket_count):
    """Generate appropriate Slack title based on notification type"""
    issue_type = ticket_group.get('issue_type', '')
    
    # Consolidated groups notification
    if 'groups' in ticket_group and 'total_tickets' in ticket_group:
        groups = ticket_group.get('groups', [])
        total_tickets = ticket_group.get('total_tickets', 0)
        
        if issue_type.startswith('Custom Query:'):
            return f"📊 Query Results: {len(groups)} Issue Categories Found ({total_tickets} Total Tickets)"
        else:
            return f"🚨 Alert: {len(groups)} Issue Groups Found ({total_tickets} Total Tickets)"
    
    # Single group notification
    if issue_type.startswith('Custom Query:'):
        return f"📊 Query Results: {ticket_count} Tickets Found"
    else:
        return f"🚨 Alert: {ticket_count} Similar Support Tickets Detected"

def build_display_text(issue_type, summary, time_window_info, is_large_result_set, ticket_count, parsed_data):
    """Build the main display text for notifications"""
    # Sanitize OpenAI-generated text that could contain problematic quotes
    issue_type = sanitize_text_for_slack(issue_type)
    summary = sanitize_text_for_slack(summary) if summary else issue_type
    
    main_text = summary if summary else issue_type
    
    if issue_type.startswith('Custom Query:'):
        query_text = issue_type.replace('Custom Query: ', '')
        display_text = f"*Query:* {query_text}\n\n*Result:* {main_text}"
        
        if time_window_info:
            time_desc = time_window_info.get('description', 'Unknown time window')
            display_text += f"\n\n*Time Window:* {time_desc}"
            
            reasoning = time_window_info.get('reasoning', '')
            if reasoning and not reasoning.startswith('Extracted from query'):
                display_text += f"\n\n*Note:* {reasoning}"
        
        if is_large_result_set:
            display_text += f"\n\n*Note:* Large result set ({ticket_count} tickets) - showing ticket numbers only"
            display_text += f"\n\n*Zendesk Link:* <https://amplitude.zendesk.com/agent/tickets|View tickets in Zendesk>"
            
            # Add organization summary if available
            org_summary = parsed_data and parsed_data.get('metadata', {}).get('organizations')
            if org_summary:
                org_list = []
                for org_name, org_info in org_summary.items():
                    count = org_info.get('count', 0)
                    org_id = org_info.get('org_id', '')
                    if org_id:
                        org_list.append(f"{org_name} ({org_id}): {count} tickets")
                    else:
                        org_list.append(f"{org_name}: {count} tickets")
                
                if org_list:
                    display_orgs = org_list[:5]
                    if len(org_list) > 5:
                        display_orgs.append(f"... and {len(org_list) - 5} more organizations")
                    display_text += f"\n\n*Organizations:* {', '.join(display_orgs)}"
    else:
        display_text = f"*Issue Type:* {main_text}"
    
    return truncate_text(display_text)

def build_ticket_links(tickets, is_large_result_set):
    """Build ticket links based on result set size"""
    if is_large_result_set:
        logger.info(f"Processing large result set with {len(tickets)} tickets - using compact format")
        ticket_links = []
        for ticket in tickets:
            ticket_id = get_ticket_data(ticket)['id']
            ticket_links.append(f"#{ticket_id}" if ticket_id != 'Unknown' else f"#{ticket_id}")
        return ticket_links
    else:
        logger.info(f"Processing standard result set with {len(tickets)} tickets")
        ticket_links = []
        for ticket in tickets:
            displays = build_ticket_display(ticket)
            if isinstance(displays, list):
                ticket_links.extend(displays)
            else:
                ticket_links.append(displays)
        return ticket_links

def format_ticket_list(ticket_links, is_large_result_set):
    """Format ticket list based on result set size"""
    if is_large_result_set:
        ticket_list = ", ".join(ticket_links)
        if len(ticket_list) > SLACK_MAX_TEXT_LENGTH:
            logger.warning(f"Slack message too long ({len(ticket_list)} chars > {SLACK_MAX_TEXT_LENGTH} limit)")
            
            visible_links = []
            current_length = 0
            for link in ticket_links:
                if current_length + len(link) + 2 < SLACK_MAX_TEXT_LENGTH - 50:
                    visible_links.append(link)
                    current_length += len(link) + 2
                else:
                    break
            
            remaining_count = len(ticket_links) - len(visible_links)
            ticket_list = ", ".join(visible_links) + f" ... and {remaining_count} more"
            logger.warning(f"Displaying {len(visible_links)} tickets, truncated {remaining_count}")
        
        return ticket_list
    else:
        return truncate_ticket_list(ticket_links)

def build_compact_groups_display(groups, total_tickets):
    """Build compact display for large result sets with multiple groups"""
    group_summaries = []
    for group in groups:
        issue_type = sanitize_text_for_slack(group.get('issue_type', 'Unknown Issue'))
        ticket_count = get_group_ticket_count(group)
        group_summaries.append(f"• *{issue_type}*: {ticket_count} tickets")
    
    return "\n".join(group_summaries)

def build_detailed_groups_display(groups):
    """Build detailed display for smaller result sets with multiple groups"""
    group_displays = []
    
    for i, group in enumerate(groups, 1):
        issue_type = sanitize_text_for_slack(group.get('issue_type', 'Unknown Issue'))
        tickets = group.get('tickets', [])
        ticket_count = get_group_ticket_count(group)
        
        group_header = f"• *Group {i}: {issue_type}* ({ticket_count} tickets)"
        group_displays.append(group_header)
        
        # Build ticket displays for this group
        for ticket in tickets:
            displays = build_ticket_display(ticket, "    ")
            if isinstance(displays, list):
                group_displays.extend(displays)
            else:
                group_displays.append(displays)
        
        # Add empty line between groups (except for the last group)
        if i < len(groups):
            group_displays.append("")
    
    return "\n".join(group_displays)

def build_single_group_detailed_display(tickets, issue_type):
    """Build detailed display for single group with bullet point formatting"""
    # Sanitize OpenAI-generated issue type
    issue_type = sanitize_text_for_slack(issue_type)
    
    # Determine group header
    if issue_type.startswith('Custom Query:'):
        group_header = f"• *Query Results* ({len(tickets)} tickets)"
    else:
        group_header = f"• *{issue_type}* ({len(tickets)} tickets)"
    
    ticket_displays = [group_header]
    
    # Build ticket displays
    for ticket in tickets:
        displays = build_ticket_display(ticket, "    ")
        if isinstance(displays, list):
            ticket_displays.extend(displays)
        else:
            ticket_displays.append(displays)
    
    return "\n".join(ticket_displays)

def send_slack_notification(ticket_group):
    """Send a Slack notification about tickets or groups"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set, skipping Slack notification")
        return False
    
    # Check if this is a consolidated groups notification
    if 'groups' in ticket_group and 'total_tickets' in ticket_group:
        return send_consolidated_groups_notification(ticket_group, webhook_url)
    
    # Handle single group
    tickets = ticket_group.get('tickets', [])
    summary = ticket_group.get('summary', '')
    parsed_data = ticket_group.get('parsed_data', {})
    time_window_info = ticket_group.get('time_window_info', {})
    is_large_result_set = ticket_group.get('is_large_result_set', False)
    issue_type = ticket_group.get('issue_type', 'Unknown Issue')
    
    ticket_count = len(tickets)
    title = generate_slack_title(ticket_group, ticket_count)
    
    # Build content based on result set size
    if is_large_result_set:
        ticket_links = build_ticket_links(tickets, True)
        ticket_list = format_ticket_list(ticket_links, True)
    else:
        ticket_list = build_single_group_detailed_display(tickets, issue_type)
    
    display_text = build_display_text(issue_type, summary, time_window_info, is_large_result_set, ticket_count, parsed_data)
    
    message = create_slack_message(title, display_text, ticket_list)
    return send_slack_message(message, webhook_url)

def send_consolidated_groups_notification(ticket_group, webhook_url):
    """Handle consolidated groups notification"""
    groups = ticket_group.get('groups', [])
    total_tickets = ticket_group.get('total_tickets', 0)
    summary = sanitize_text_for_slack(ticket_group.get('summary', ''))
    time_window_info = ticket_group.get('time_window_info', {})
    
    is_large_result_set = total_tickets > LARGE_RESULT_THRESHOLD
    title = f"🚨 Alert: {len(groups)} Issue Groups Found ({total_tickets} Total Tickets)"
    
    # Build group display
    if is_large_result_set:
        group_display = build_compact_groups_display(groups, total_tickets)
    else:
        group_display = build_detailed_groups_display(groups)
    
    # Build main display text
    issue_type = sanitize_text_for_slack(ticket_group.get('issue_type', ''))
    if issue_type.startswith('Custom Query:'):
        query_text = issue_type.replace('Custom Query: ', '')
        display_text = f"*Query:* {query_text}\n\n*Summary:* {summary}"
        
        if time_window_info:
            time_desc = time_window_info.get('description', 'Unknown time window')
            display_text += f"\n\n*Time Window:* {time_desc}"
    else:
        display_text = f"*Summary:* {summary}"
    
    if is_large_result_set:
        display_text += f"\n\n*Note:* Large result set ({total_tickets} tickets) - showing group summaries only"
        display_text += f"\n\n*Zendesk Link:* <https://amplitude.zendesk.com/agent/tickets|View tickets in Zendesk>"
    
    message = create_slack_message(title, display_text, group_display)
    return send_slack_message(message, webhook_url)

def create_slack_message(title, display_text, content):
    """Create Slack message structure"""
    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": truncate_text(title, 150)
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
                    "text": f"*Details:*\n{content}"
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
            }
        ]
    }

def send_slack_message(message, webhook_url):
    """Send message to Slack"""
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