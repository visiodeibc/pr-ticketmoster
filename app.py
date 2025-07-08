import time
import schedule
from datetime import datetime
import json
import os
import logging
import sys
from ticket_analyzer import analyze_similar_tickets, analyze_tickets_with_query_and_timeframe
from slack_notifier import send_slack_notification
from zendesk_client import fetch_recent_tickets
from constants import MIN_TICKETS_FOR_GROUP

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('zendesk_alert')

def enrich_clustering_groups_with_org_data(groups, original_tickets):
    """Enrich clustering groups with full ticket data from original Zendesk tickets"""
    if not groups or not original_tickets:
        return groups
    
    ticket_lookup = {str(ticket['id']): ticket for ticket in original_tickets}
    enriched_groups = []
    
    for group in groups:
        enriched_group = group.copy()
        
        # Get ticket IDs from the unified format
        ticket_ids = group.get('ticket_ids', [])
        enriched_tickets = []
        
        for ticket_id in ticket_ids:
            if str(ticket_id) in ticket_lookup:
                enriched_tickets.append(ticket_lookup[str(ticket_id)].copy())
                logger.debug(f"Enriched clustering ticket #{ticket_id} with org_id: {ticket_lookup[str(ticket_id)].get('numeric_org_id', 'N/A')}")
            else:
                logger.warning(f"Could not find original data for clustering ticket #{ticket_id}")
        
        enriched_group['tickets'] = enriched_tickets
        enriched_groups.append(enriched_group)
        logger.info(f"Enriched clustering group '{group.get('issue_type')}' with {len(enriched_tickets)} tickets")
    
    return enriched_groups

def load_tickets():
    """Load tickets from Zendesk API or fallback to sample data"""
    tickets = fetch_recent_tickets()
    
    if tickets:
        logger.info(f"Loaded {len(tickets)} tickets from Zendesk")
        return tickets
    
    logger.info("Using sample tickets for testing")
    try:
        with open('sample_tickets.json', 'r') as f:
            return json.load(f)
    except Exception:
        logger.error("No tickets available")
        return []

def get_qualifying_groups(enriched_groups):
    """Filter groups that meet the alert threshold"""
    threshold = int(os.environ.get('TICKET_CNT_THRESHOLD', str(MIN_TICKETS_FOR_GROUP)))
    qualifying_groups = []
    total_tickets = 0
    
    logger.info(f"Using alert threshold: {threshold} tickets")
    
    for group in enriched_groups:
        ticket_count = len(group['tickets'])
        logger.info(f"Found group '{group['issue_type']}' with {ticket_count} tickets")
        
        if ticket_count >= threshold:
            logger.info(f"Qualifying group: {ticket_count} tickets with '{group['issue_type']}'")
            qualifying_groups.append(group)
            total_tickets += ticket_count
        else:
            logger.info(f"Skipping alert for '{group['issue_type']}' - {ticket_count} tickets < {threshold} threshold")
    
    return qualifying_groups, total_tickets

def send_consolidated_alert(qualifying_groups, total_tickets):
    """Send consolidated alert for qualifying groups"""
    logger.info(f"Sending consolidated alert for {len(qualifying_groups)} groups with {total_tickets} total tickets")
    
    consolidated_alert = {
        'issue_type': 'Multiple Issue Groups Detected',
        'groups': qualifying_groups,
        'total_tickets': total_tickets,
        'summary': f"Found {len(qualifying_groups)} groups of similar issues affecting {total_tickets} tickets"
    }
    
    if send_slack_notification(consolidated_alert):
        logger.info("✓ Consolidated alert sent successfully")
        return True
    else:
        logger.error("✗ Failed to send consolidated alert")
        return False

def analyze_with_custom_query(custom_query):
    """Analyze tickets with a custom query and send results to Slack"""
    # Sanitize query input - remove problematic characters that could break JSON parsing
    custom_query = custom_query.strip()
    if custom_query.endswith('{') or custom_query.endswith('}'):
        custom_query = custom_query.rstrip('{}').strip()
        logger.info(f"Sanitized query by removing trailing braces: {custom_query}")
    
    logger.info(f"Running custom query: {custom_query}")
    
    # Use the query analysis function that handles time windows
    parsed_data, summary, time_window_info = analyze_tickets_with_query_and_timeframe(None, custom_query)
    
    logger.info(f"Query completed. Time window used: {time_window_info}")
    print(f"\n=== QUERY SUMMARY ===\n{summary}")
    
    if time_window_info:
        print(f"\n=== TIME WINDOW INFO ===")
        print(f"Description: {time_window_info.get('description', 'Unknown')}")
        print(f"Hours: {time_window_info.get('hours', 'Unknown')}")
        print(f"Has time reference: {time_window_info.get('has_time_reference', False)}")
        print(f"Reasoning: {time_window_info.get('reasoning', 'No reasoning provided')}")
    
    # Extract groups from unified format
    query_groups = []
    total_tickets = 0
    is_large_result_set = False
    
    if parsed_data and isinstance(parsed_data, dict):
        response_type = parsed_data.get('response_type', 'unknown')
        logger.info(f"Response type: {response_type}")
        
        # Get OpenAI's suggestion but enforce our own logic
        openai_large_result_set = parsed_data.get('large_result_set', False)
        logger.info(f"OpenAI suggested large result set: {openai_large_result_set}")
        
        data = parsed_data.get('data', {})
        logger.info(f"Data section keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        
        if isinstance(data, dict):
            # Handle new groups format
            if 'groups' in data and data['groups']:
                query_groups = data['groups']
                # Use count field from OpenAI or fall back to counting ticket IDs
                total_tickets = 0
                for group in query_groups:
                    # First try the count field from OpenAI
                    group_count = group.get('count', 0)
                    if group_count == 0:
                        # Fallback: count from ticket_ids array
                        ticket_ids_count = len(group.get('ticket_ids', []))
                        group_count = ticket_ids_count
                    total_tickets += group_count
                logger.info(f"Extracted {len(query_groups)} groups with {total_tickets} total tickets from groups format")
            
            # Legacy fallback for old format  
            elif 'ticket_ids' in data:
                logger.info("Using legacy format - converting to groups structure")
                ticket_ids = data.get('ticket_ids', [])
                total_tickets = len(ticket_ids)
                
                # Create a single group for legacy format
                query_groups = [{
                    'issue_type': 'Query Results',
                    'ticket_ids': ticket_ids,
                    'count': total_tickets
                }]
                logger.info(f"Converted legacy format to 1 group with {total_tickets} tickets")
            
            # Override OpenAI's large_result_set decision with our own logic
            from constants import LARGE_RESULT_THRESHOLD
            is_large_result_set = total_tickets > LARGE_RESULT_THRESHOLD
            if is_large_result_set != openai_large_result_set:
                logger.info(f"Overriding OpenAI large_result_set ({openai_large_result_set}) with our logic ({is_large_result_set}) based on {total_tickets} tickets vs {LARGE_RESULT_THRESHOLD} threshold")
            else:
                logger.info(f"OpenAI large_result_set decision matches our logic: {is_large_result_set}")
            
            logger.info(f"Final: {len(query_groups)} groups, {total_tickets} total tickets")
    
    # Send to Slack with unified groups format
    if len(query_groups) == 1:
        # Single group - send as individual group notification
        single_group = query_groups[0]
        
        # Always convert ticket_ids to enriched ticket format since OpenAI only returns IDs
        ticket_ids = single_group.get('ticket_ids', [])
        if ticket_ids:
            # Get the original tickets used for analysis to enrich the response
            from ticket_analyzer import get_tickets_for_timeframe
            analysis_tickets = get_tickets_for_timeframe(None, time_window_info, None)
            ticket_lookup = {str(ticket['id']): ticket for ticket in analysis_tickets}
            
            # Create enriched ticket objects for Slack display
            enriched_tickets = []
            for ticket_id in ticket_ids:
                if str(ticket_id) in ticket_lookup:
                    original_ticket = ticket_lookup[str(ticket_id)]
                    enriched_ticket = {
                        "id": ticket_id,
                        "subject": original_ticket.get('subject', ''),
                        "org_id": original_ticket.get('numeric_org_id', ''),
                        "assignee": original_ticket.get('assignee', ''),
                        "jira_id": original_ticket.get('jira_id', ''),
                        "jira_ticket_id": original_ticket.get('jira_ticket_id', ''),
                        "link_to_discourse": original_ticket.get('link_to_discourse', '')
                    }
                    enriched_tickets.append(enriched_ticket)
        else:
            enriched_tickets = []
        
        slack_payload = {
            "issue_type": f"Custom Query: {custom_query}",
            "tickets": enriched_tickets,
            "summary": summary,
            "parsed_data": parsed_data,
            "time_window_info": time_window_info,
            "is_large_result_set": is_large_result_set
        }
    else:
        # Multiple groups - send as consolidated groups notification
        # Enrich all groups with original ticket data
        if query_groups:
            from ticket_analyzer import get_tickets_for_timeframe
            analysis_tickets = get_tickets_for_timeframe(None, time_window_info, None)
            ticket_lookup = {str(ticket['id']): ticket for ticket in analysis_tickets}
            
            enriched_groups = []
            for group in query_groups:
                enriched_group = group.copy()
                ticket_ids = group.get('ticket_ids', [])
                
                # Create enriched ticket objects for this group
                enriched_tickets = []
                for ticket_id in ticket_ids:
                    if str(ticket_id) in ticket_lookup:
                        original_ticket = ticket_lookup[str(ticket_id)]
                        enriched_ticket = {
                            "id": ticket_id,
                            "subject": original_ticket.get('subject', ''),
                            "org_id": original_ticket.get('numeric_org_id', ''),
                            "assignee": original_ticket.get('assignee', ''),
                            "jira_id": original_ticket.get('jira_id', ''),
                            "jira_ticket_id": original_ticket.get('jira_ticket_id', ''),
                            "link_to_discourse": original_ticket.get('link_to_discourse', '')
                        }
                        enriched_tickets.append(enriched_ticket)
                
                enriched_group['tickets'] = enriched_tickets
                enriched_groups.append(enriched_group)
        else:
            enriched_groups = query_groups
        
        slack_payload = {
            "issue_type": f"Custom Query: {custom_query}",
            "groups": enriched_groups,
            "total_tickets": total_tickets,
            "summary": summary,
            "parsed_data": parsed_data,
            "time_window_info": time_window_info,
            "is_large_result_set": is_large_result_set
        }
    
    if send_slack_notification(slack_payload):
        logger.info("✓ Custom query summary sent to Slack")
        return True
    else:
        logger.error("✗ Failed to send custom query summary to Slack")
        return False

def check_for_alerts():
    """Main function to check for similar issues and send alerts"""
    logger.info("Checking for similar ticket patterns...")
    
    tickets = load_tickets()
    if not tickets:
        return
    
    similar_groups = analyze_similar_tickets(tickets)
    logger.info("Enriching clustering groups with complete ticket data...")
    enriched_groups = enrich_clustering_groups_with_org_data(similar_groups, tickets)
    
    qualifying_groups, total_tickets = get_qualifying_groups(enriched_groups)
    
    if qualifying_groups:
        send_consolidated_alert(qualifying_groups, total_tickets)
    else:
        logger.info("No qualifying groups found - no alerts sent")
    
    logger.info(f"Check complete. Groups analyzed: {len(similar_groups)}, Groups alerted: {len(qualifying_groups)}")

def run_once():
    """Run a single check without scheduling"""
    check_for_alerts()

def run_scheduler():
    """Run hourly checks with scheduler"""
    logger.info("Starting Zendesk Alert System (hourly checks)")
    
    check_for_alerts()  # Initial check
    schedule.every(1).hour.do(check_for_alerts)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Stopped")
            break

def show_help():
    """Show usage instructions"""
    print("""
🤖 Zendesk Alert System

Usage:
    python app.py [command] [options]

Commands:
    --once          Run a single check for similar tickets (default)
    --monitor       Run continuous monitoring with hourly checks
    --query "text"  Analyze tickets with custom query and send to Slack
    --help          Show this help message

Examples:
    python app.py                                    # Single check
    python app.py --once                            # Single check  
    python app.py --monitor                         # Continuous monitoring
    python app.py --query "How many login issues?"  # Custom analysis
    python app.py --query "What are the top SDK problems this week?"
    
Environment Variables:
    ZENDESK_URL, ZENDESK_EMAIL, ZENDESK_TOKEN      # Required
    OPENAI_API_KEY                                  # Required for AI analysis
    SLACK_WEBHOOK_URL                               # Optional for notifications
    TICKET_CNT_THRESHOLD                            # Alert threshold (default: 5)
    """)

if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "--help":
            show_help()
        elif command == "--monitor":
            run_scheduler()
        elif command == "--once":
            run_once()
        elif command == "--query":
            if len(sys.argv) < 3:
                logger.error("No query provided. Usage: python app.py --query 'your question here'")
                sys.exit(1)
            custom_query = " ".join(sys.argv[2:])
            analyze_with_custom_query(custom_query)
        else:
            logger.error(f"Unknown command: {command}")
            show_help()
            sys.exit(1)
    else:
        # Default behavior: run once
        run_once() 