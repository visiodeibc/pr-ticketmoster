import os
import requests
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from constants import SLACK_MAX_TEXT_LENGTH, SLACK_MAX_BLOCKS, JIRA_BASE_URL, LARGE_RESULT_THRESHOLD
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
    """Truncate ticket list to fit Slack limits, handling indented sub-items"""
    if not ticket_links:
        return "No tickets found"
    
    result = ""
    truncated_count = 0
    main_ticket_count = 0
    
    for i, link in enumerate(ticket_links):
        test_result = result + link + "\n"
        if len(test_result) > max_length - 100:  # Leave room for truncation message
            # Count remaining main tickets (not indented sub-items)
            remaining_items = ticket_links[i:]
            for item in remaining_items:
                if not item.startswith('    '):  # Main ticket, not sub-item
                    truncated_count += 1
            break
        result = test_result
        
        # Count main tickets for proper truncation message
        if not link.startswith('    '):  # Main ticket, not sub-item
            main_ticket_count += 1
    
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
    
    # Check if this is a consolidated groups notification
    if 'groups' in ticket_group and 'total_tickets' in ticket_group:
        groups = ticket_group.get('groups', [])
        total_tickets = ticket_group.get('total_tickets', 0)
        
        # Differentiate between clustering alerts and query results with multiple groups
        if issue_type.startswith('Custom Query:'):
            return f"📊 Query Results: {len(groups)} Issue Categories Found ({total_tickets} Total Tickets)"
        else:
            return f"🚨 Alert: {len(groups)} Issue Groups Found ({total_tickets} Total Tickets)"
    
    # Check if this is a custom query (starts with "Custom Query:")
    if issue_type.startswith('Custom Query:'):
        return f"📊 Query Results: {ticket_count} Tickets Found"
    else:
        # This is a clustering alert
        return f"🚨 Alert: {ticket_count} Similar Support Tickets Detected"

def send_slack_notification(ticket_group):
    """
    Send a Slack notification about a group of similar tickets or consolidated groups
    
    Args:
        ticket_group: Dictionary containing either:
            Single group:
            - issue_type: Type of issue
            - tickets: List of tickets in the group
            - summary: (optional) Summary text for queries
            - parsed_data: (optional) Full parsed data from OpenAI
            - time_window_info: (optional) Time window information for queries
            - is_large_result_set: (optional) Flag for large result sets
            
            Consolidated groups:
            - issue_type: "Multiple Issue Groups Detected"
            - groups: List of group objects
            - total_tickets: Total number of tickets across all groups
            - summary: Summary of all groups
    
    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set, skipping Slack notification")
        return False
    
    issue_type = ticket_group.get('issue_type', 'Unknown Issue')
    
    # Check if this is a consolidated groups notification (clustering or multi-group query results)
    if 'groups' in ticket_group and 'total_tickets' in ticket_group:
        return send_consolidated_groups_notification(ticket_group, webhook_url)
    
    # Handle single group (existing logic)
    tickets = ticket_group.get('tickets', [])
    summary = ticket_group.get('summary', '')
    parsed_data = ticket_group.get('parsed_data', {})
    time_window_info = ticket_group.get('time_window_info', {})
    is_large_result_set = ticket_group.get('is_large_result_set', False)
    
    ticket_count = len(tickets)
    
    # Generate title
    title = generate_slack_title(ticket_group, ticket_count)
    
    # Build content based on result set size
    if is_large_result_set:
        # For large result sets, use compact format
        ticket_links = build_ticket_links(tickets, True)
        ticket_list = format_ticket_list(ticket_links, True)
    else:
        # For smaller result sets, use the new detailed bullet point format
        ticket_list = build_single_group_detailed_display(tickets, issue_type)
    
    # Build display text
    display_text = build_display_text(issue_type, summary, time_window_info, is_large_result_set, ticket_count, parsed_data)
    
    # Create and send message
    message = create_slack_message(title, display_text, ticket_list)
    return send_slack_message(message, webhook_url)

def send_consolidated_groups_notification(ticket_group, webhook_url):
    """Handle consolidated groups notification"""
    
    groups = ticket_group.get('groups', [])
    total_tickets = ticket_group.get('total_tickets', 0)
    summary = ticket_group.get('summary', '')
    time_window_info = ticket_group.get('time_window_info', {})
    
    # Determine if this is a large result set based on total tickets
    is_large_result_set = total_tickets > LARGE_RESULT_THRESHOLD
    
    # Generate title
    title = f"🚨 Alert: {len(groups)} Issue Groups Found ({total_tickets} Total Tickets)"
    
    # Build group display
    if is_large_result_set:
        # Compact format for large result sets
        group_display = build_compact_groups_display(groups, total_tickets)
    else:
        # Detailed format for smaller result sets  
        group_display = build_detailed_groups_display(groups)
    
    # Build main display text with context awareness
    issue_type = ticket_group.get('issue_type', '')
    if issue_type.startswith('Custom Query:'):
        query_text = issue_type.replace('Custom Query: ', '')
        display_text = f"*Query:* {query_text}\n\n*Summary:* {summary}"
        
        # Add time window info for query results
        if time_window_info:
            time_desc = time_window_info.get('description', 'Unknown time window')
            display_text += f"\n\n*Time Window:* {time_desc}"
    else:
        display_text = f"*Summary:* {summary}"
    
    if is_large_result_set:
        display_text += f"\n\n*Note:* Large result set ({total_tickets} tickets) - showing group summaries only"
        display_text += f"\n\n*Zendesk Link:* <https://amplitude.zendesk.com/agent/tickets|View tickets in Zendesk>"
    
    # Create and send message
    message = create_slack_message(title, display_text, group_display)
    return send_slack_message(message, webhook_url) 

def build_ticket_links(tickets, is_large_result_set):
    """Build ticket links based on result set size"""
    ticket_links = []
    
    if is_large_result_set:
        # For large result sets, use ultra-compact format with just ticket numbers
        logger.info(f"Processing large result set with {len(tickets)} tickets - using compact format")
        for ticket in tickets:
            ticket_id = ticket.get('ticket_id') or ticket.get('id', 'Unknown')
            if ticket_id and ticket_id != 'Unknown':
                ticket_links.append(f"#{ticket_id}")
            else:
                ticket_links.append(f"#{ticket_id}")
    else:
        # For smaller result sets, use detailed format with full links
        logger.info(f"Processing standard result set with {len(tickets)} tickets")
        for ticket in tickets:
            ticket_id = get_ticket_id(ticket)
            subject = get_ticket_subject(ticket)
            org_name = ticket.get('org_name', '')
            org_id = ticket.get('org_id', '') or ticket.get('numeric_org_id', '')
            assignee = ticket.get('assignee', '')
            jira_id = ticket.get('jira_id', '')
            jira_ticket_id = ticket.get('jira_ticket_id', '')
            discourse_link = ticket.get('link_to_discourse', '')
            
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
                
                # Add JIRA and Discourse links with indentation if available
                additional_links = []
                
                # Handle JIRA links
                if jira_id or jira_ticket_id:
                    if jira_id and jira_ticket_id:
                        jira_link = f"    📋 JIRA: <{JIRA_BASE_URL}/{jira_ticket_id}|{jira_ticket_id}> (ID: {jira_id})"
                    elif jira_ticket_id:
                        jira_link = f"    📋 JIRA: <{JIRA_BASE_URL}/{jira_ticket_id}|{jira_ticket_id}>"
                    elif jira_id:
                        jira_link = f"    📋 JIRA ID: {jira_id}"
                    additional_links.append(jira_link)
                
                # Handle Discourse links
                if discourse_link:
                    if discourse_link.startswith('http'):
                        discourse_display = f"    💬 Discourse: <{discourse_link}|View Discussion>"
                    else:
                        discourse_display = f"    💬 Discourse: {discourse_link}"
                    additional_links.append(discourse_display)
                
                # Add additional links if any exist
                if additional_links:
                    ticket_links.extend(additional_links)
            else:
                ticket_links.append(f"Unknown ID - {subject}")
    
    return ticket_links

def format_ticket_list(ticket_links, is_large_result_set):
    """Format ticket list based on result set size"""
    if is_large_result_set:
        # Join with commas for maximum compactness
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

def build_display_text(issue_type, summary, time_window_info, is_large_result_set, ticket_count, parsed_data):
    """Build the main display text for single group notifications"""
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
                    display_orgs = org_list[:5]
                    if len(org_list) > 5:
                        display_orgs.append(f"... and {len(org_list) - 5} more organizations")
                    display_text += f"\n\n*Organizations:* {', '.join(display_orgs)}"
    else:
        display_text = f"*Issue Type:* {main_text}"
    
    return truncate_text(display_text)

def build_compact_groups_display(groups, total_tickets):
    """Build compact display for large result sets with multiple groups"""
    group_summaries = []
    for group in groups:
        issue_type = group.get('issue_type', 'Unknown Issue')
        
        # For large result sets, count tickets from ticket_ids array; for small sets, count from tickets array
        ticket_count = group.get('count', 0)  # First try the count field from OpenAI
        if ticket_count == 0:
            # Fallback: count from either tickets (detailed) or ticket_ids (large result set)
            tickets_count = len(group.get('tickets', []))
            ticket_ids_count = len(group.get('ticket_ids', []))
            ticket_count = tickets_count if tickets_count > 0 else ticket_ids_count
        
        # Use consistent bullet point formatting
        group_summaries.append(f"• *{issue_type}*: {ticket_count} tickets")
    
    return "\n".join(group_summaries)

def build_detailed_groups_display(groups):
    """Build detailed display for smaller result sets with multiple groups"""
    group_displays = []
    
    for i, group in enumerate(groups, 1):
        issue_type = group.get('issue_type', 'Unknown Issue')
        tickets = group.get('tickets', [])
        
        # Count tickets correctly for both large and small result sets
        ticket_count = group.get('count', 0)  # First try the count field from OpenAI
        if ticket_count == 0:
            # Fallback: count from either tickets (detailed) or ticket_ids (large result set)  
            tickets_count = len(tickets)
            ticket_ids_count = len(group.get('ticket_ids', []))
            ticket_count = tickets_count if tickets_count > 0 else ticket_ids_count
        
        # Use bullet point for group header with proper indentation
        group_header = f"• *Group {i}: {issue_type}* ({ticket_count} tickets)"
        group_displays.append(group_header)
        
        # Build ticket links for this group with deeper indentation
        for ticket in tickets:
            ticket_id = get_ticket_id(ticket)
            subject = get_ticket_subject(ticket)
            org_name = ticket.get('org_name', '')
            org_id = ticket.get('org_id', '') or ticket.get('numeric_org_id', '')
            assignee = ticket.get('assignee', '')
            jira_id = ticket.get('jira_id', '')
            jira_ticket_id = ticket.get('jira_ticket_id', '')
            discourse_link = ticket.get('link_to_discourse', '')
            
            if ticket_id:
                zendesk_url = f"https://amplitude.zendesk.com/agent/tickets/{ticket_id}"
                
                # Build ticket display with bullet point and deeper indentation (4 spaces)
                ticket_display = f"    • <{zendesk_url}|#{ticket_id}> - {subject}"
                
                # Add organization info if available
                if org_name and org_id:
                    ticket_display += f" (Org: {org_name} - {org_id})"
                elif org_id:
                    ticket_display += f" (Org ID: {org_id})"
                
                # Add assignee info if available
                if assignee:
                    ticket_display += f" [Assigned: {assignee}]"
                
                group_displays.append(ticket_display)
                
                # Add JIRA and Discourse links with even deeper indentation (8 spaces)
                # Handle JIRA links
                if jira_id or jira_ticket_id:
                    logger.debug(f"Processing JIRA links for ticket {ticket_id}: jira_id={jira_id}, jira_ticket_id={jira_ticket_id}")
                    
                    # Check if we have a proper JIRA ticket ID
                    clickable_jira_id = None
                    if jira_ticket_id and jira_ticket_id.strip():
                        clickable_jira_id = jira_ticket_id.strip()
                    elif jira_id and jira_id.strip():
                        # Check if jira_id looks like a ticket identifier (e.g., "AMP-134406")
                        jira_id_cleaned = jira_id.strip()
                        if '-' in jira_id_cleaned and any(c.isalpha() for c in jira_id_cleaned):
                            clickable_jira_id = jira_id_cleaned
                    
                    if clickable_jira_id:
                        # Make JIRA link clickable with proper URL (8 spaces indentation)
                        jira_url = f"{JIRA_BASE_URL}/{clickable_jira_id}"
                        jira_link = f"        📋 JIRA: <{jira_url}|{clickable_jira_id}>"
                        logger.debug(f"Created clickable JIRA link: {jira_link}")
                        group_displays.append(jira_link)
                    elif jira_id and jira_id.strip():
                        # Fallback for numeric or other JIRA IDs (8 spaces indentation)
                        jira_link = f"        📋 JIRA ID: {jira_id.strip()}"
                        logger.debug(f"Created JIRA ID display: {jira_link}")
                        group_displays.append(jira_link)
                
                # Handle Discourse links
                if discourse_link and discourse_link.strip():
                    logger.debug(f"Processing Discourse link for ticket {ticket_id}: {discourse_link}")
                    
                    discourse_link = discourse_link.strip()
                    if discourse_link.startswith('http'):
                        discourse_display = f"        💬 Discourse: <{discourse_link}|View Discussion>"
                    else:
                        discourse_display = f"        💬 Discourse: {discourse_link}"
                    logger.debug(f"Created Discourse link: {discourse_display}")
                    group_displays.append(discourse_display)
            else:
                group_displays.append(f"    • #{ticket_id or 'Unknown'} - {subject}")
        
        # Add empty line between groups (except for the last group)
        if i < len(groups):
            group_displays.append("")
    
    return "\n".join(group_displays)

def build_single_group_detailed_display(tickets, issue_type):
    """Build detailed display for single group (including query results) with bullet point formatting"""
    ticket_displays = []
    
    # Determine group header based on issue type
    if issue_type.startswith('Custom Query:'):
        group_header = f"• *Query Results* ({len(tickets)} tickets)"
    else:
        group_header = f"• *{issue_type}* ({len(tickets)} tickets)"
    
    ticket_displays.append(group_header)
    
    # Build ticket links with consistent indentation
    for ticket in tickets:
        ticket_id = get_ticket_id(ticket)
        subject = get_ticket_subject(ticket)
        org_name = ticket.get('org_name', '')
        org_id = ticket.get('org_id', '') or ticket.get('numeric_org_id', '')
        assignee = ticket.get('assignee', '')
        jira_id = ticket.get('jira_id', '')
        jira_ticket_id = ticket.get('jira_ticket_id', '')
        discourse_link = ticket.get('link_to_discourse', '')
        
        if ticket_id:
            zendesk_url = f"https://amplitude.zendesk.com/agent/tickets/{ticket_id}"
            
            # Build ticket display with bullet point and indentation (4 spaces)
            ticket_display = f"    • <{zendesk_url}|#{ticket_id}> - {subject}"
            
            # Add organization info if available
            if org_name and org_id:
                ticket_display += f" (Org: {org_name} - {org_id})"
            elif org_id:
                ticket_display += f" (Org ID: {org_id})"
            
            # Add assignee info if available
            if assignee:
                ticket_display += f" [Assigned: {assignee}]"
            
            ticket_displays.append(ticket_display)
            
            # Add JIRA and Discourse links with deeper indentation (8 spaces)
            # Handle JIRA links
            if jira_id or jira_ticket_id:
                logger.debug(f"Processing JIRA links for ticket {ticket_id}: jira_id={jira_id}, jira_ticket_id={jira_ticket_id}")
                
                # Check if we have a proper JIRA ticket ID
                clickable_jira_id = None
                if jira_ticket_id and jira_ticket_id.strip():
                    clickable_jira_id = jira_ticket_id.strip()
                elif jira_id and jira_id.strip():
                    # Check if jira_id looks like a ticket identifier (e.g., "AMP-134406")
                    jira_id_cleaned = jira_id.strip()
                    if '-' in jira_id_cleaned and any(c.isalpha() for c in jira_id_cleaned):
                        clickable_jira_id = jira_id_cleaned
                
                if clickable_jira_id:
                    # Make JIRA link clickable with proper URL (8 spaces indentation)
                    jira_url = f"{JIRA_BASE_URL}/{clickable_jira_id}"
                    jira_link = f"        📋 JIRA: <{jira_url}|{clickable_jira_id}>"
                    logger.debug(f"Created clickable JIRA link: {jira_link}")
                    ticket_displays.append(jira_link)
                elif jira_id and jira_id.strip():
                    # Fallback for numeric or other JIRA IDs (8 spaces indentation)
                    jira_link = f"        📋 JIRA ID: {jira_id.strip()}"
                    logger.debug(f"Created JIRA ID display: {jira_link}")
                    ticket_displays.append(jira_link)
            
            # Handle Discourse links
            if discourse_link and discourse_link.strip():
                logger.debug(f"Processing Discourse link for ticket {ticket_id}: {discourse_link}")
                
                discourse_link = discourse_link.strip()
                if discourse_link.startswith('http'):
                    discourse_display = f"        💬 Discourse: <{discourse_link}|View Discussion>"
                else:
                    discourse_display = f"        💬 Discourse: {discourse_link}"
                logger.debug(f"Created Discourse link: {discourse_display}")
                ticket_displays.append(discourse_display)
        else:
            ticket_displays.append(f"    • #{ticket_id or 'Unknown'} - {subject}")
    
    return "\n".join(ticket_displays)

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