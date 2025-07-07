import time
import schedule
from datetime import datetime
import json
import os
import logging
from ticket_analyzer import analyze_similar_tickets
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
        enriched_tickets = []
        
        for ticket in group.get('tickets', []):
            ticket_id = str(ticket.get('id', ''))
            if ticket_id in ticket_lookup:
                enriched_tickets.append(ticket_lookup[ticket_id].copy())
                logger.debug(f"Enriched clustering ticket #{ticket_id} with org_id: {ticket_lookup[ticket_id].get('numeric_org_id', 'N/A')}")
            else:
                enriched_tickets.append(ticket)
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

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once()
    else:
        run_scheduler() 