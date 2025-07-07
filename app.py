import time
import schedule
from datetime import datetime
import json
import os
import logging
from ticket_analyzer import analyze_similar_tickets
from slack_notifier import send_slack_notification
from zendesk_client import fetch_recent_tickets, save_tickets_locally

# Simple logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('zendesk_alert')

def load_tickets():
    """Load tickets from Zendesk API or fallback to sample data"""
    # Try Zendesk API first
    tickets = fetch_recent_tickets()
    
    if tickets:
        logger.info(f"Loaded {len(tickets)} tickets from Zendesk")
        save_tickets_locally(tickets)
        return tickets
    
    # Fallback to sample data for testing
    logger.info("Using sample tickets for testing")
    try:
        with open('sample_tickets.json', 'r') as f:
            return json.load(f)
    except:
        logger.error("No tickets available")
        return []

def check_for_alerts():
    """Main function to check for similar issues and send alerts"""
    logger.info("Checking for similar ticket patterns...")
    
    # Load recent tickets
    tickets = load_tickets()
    if not tickets:
        return
    
    # Analyze for similar issues
    similar_groups = analyze_similar_tickets(tickets)
    
    # Send alerts for groups with threshold+ tickets
    threshold = int(os.environ.get('TICKET_CNT_THRESHOLD', '5'))
    alerts_sent = 0
    
    for group in similar_groups:
        ticket_count = len(group['tickets'])
        if ticket_count >= threshold:
            logger.info(f"Alert: {ticket_count} tickets with '{group['issue_type']}'")
            if send_slack_notification(group):
                alerts_sent += 1
    
    logger.info(f"Check complete. Sent {alerts_sent} alerts")

def run_once():
    """Run a single check without scheduling"""
    check_for_alerts()

def run_scheduler():
    """Run hourly checks with scheduler"""
    logger.info("Starting Zendesk Alert System (hourly checks)")
    
    # Initial check
    check_for_alerts()
    
    # Schedule hourly checks
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