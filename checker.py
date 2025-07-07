#!/usr/bin/env python3
"""
Unified testing tool for the Zendesk Alert System
Tests Zendesk API connection, ticket analysis, and Slack notifications
"""

import os
import json
import logging
import sys
from dotenv import load_dotenv
from zendesk_client import ZendeskClient, fetch_recent_tickets
from ticket_analyzer import analyze_similar_tickets, analyze_tickets_with_query
from slack_notifier import send_slack_notification
import requests
from constants import (
    REQUIRED_ENV_VARS, 
    OPTIONAL_ENV_VARS, 
    MIN_TICKETS_FOR_GROUP, 
    DEFAULT_SEND_TEST_SLACK
)

load_dotenv()

# Simple logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test')

def test_environment():
    """Test if all required environment variables are set"""
    logger.info("=== TESTING ENVIRONMENT SETUP ===")
    
    all_good = True
    
    logger.info("Required variables:")
    for var in REQUIRED_ENV_VARS:
        value = os.environ.get(var)
        if value:
            display_value = '*' * len(value) if any(x in var for x in ['TOKEN', 'KEY']) else value
            logger.info(f"  ✓ {var}: {display_value}")
        else:
            logger.error(f"  ✗ {var}: Missing")
            all_good = False
    
    logger.info("Optional variables:")
    for var in OPTIONAL_ENV_VARS:
        value = os.environ.get(var)
        if value:
            logger.info(f"  ✓ {var}: {value}")
        else:
            logger.info(f"  - {var}: Not set (using defaults)")
    
    return all_good

def test_zendesk():
    """Test Zendesk API connection and ticket retrieval"""
    logger.info("=== TESTING ZENDESK API ===")
    
    try:
        # Test client initialization
        client = ZendeskClient()
        if not client.client:
            logger.error("Failed to initialize Zendesk client")
            return False
        
        logger.info("✓ Zendesk client initialized")
        
        # Test ticket retrieval
        tickets = fetch_recent_tickets()
        
        if tickets:
            logger.info(f"✓ Retrieved {len(tickets)} tickets from last 24 hours")
            
            # Show sample ticket
            sample = tickets[0]
            logger.info("Sample ticket:")
            logger.info(f"  ID: {sample.get('id')}")
            logger.info(f"  Subject: {sample.get('subject')}")
            logger.info(f"  Status: {sample.get('status')}")
            logger.info(f"  Created: {sample.get('created_at')}")
            
            # Print all available fields (keys)
            logger.info(f"All available fields in sample ticket: {list(sample.keys())}")
            # Print full JSON of the sample ticket
            logger.info(f"Full sample ticket JSON:\n{json.dumps(sample, indent=4)}")
            logger.info(f"Ticket type: {sample}")
        else:
            logger.info("✓ API connection works (no recent tickets found)")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Zendesk API test failed: {e}")
        logger.error("Check your ZENDESK_URL, ZENDESK_EMAIL, and ZENDESK_TOKEN")
        return False

def test_analysis():
    """Test ticket analysis with sample data"""
    logger.info("=== TESTING TICKET ANALYSIS ===")
    
    try:
        # Load sample tickets
        with open('sample_tickets.json', 'r') as f:
            tickets = json.load(f)
        logger.info(f"✓ Loaded {len(tickets)} sample tickets")
        
        # Run analysis
        similar_groups = analyze_similar_tickets(tickets)
        logger.info(f"✓ Analysis complete - found {len(similar_groups)} groups")
        
        # Show results
        threshold = int(os.environ.get('TICKET_CNT_THRESHOLD', str(MIN_TICKETS_FOR_GROUP)))
        
        for i, group in enumerate(similar_groups, 1):
            ticket_count = len(group['tickets'])
            logger.info(f"Group {i}: '{group['issue_type']}' - {ticket_count} tickets")
            
            if ticket_count >= threshold:
                logger.info(f"  → Would trigger alert (>= {threshold} tickets)")
                
                # Test Slack notification if enabled
                if os.environ.get("SEND_TEST_SLACK") == "true":
                    logger.info("  → Sending test Slack notification...")
                    if send_slack_notification(group):
                        logger.info("  ✓ Test notification sent")
                    else:
                        logger.error("  ✗ Test notification failed")
        
        return True
        
    except FileNotFoundError:
        logger.error("✗ sample_tickets.json not found")
        return False
    except Exception as e:
        logger.error(f"✗ Analysis test failed: {e}")
        return False

def test_slack():
    """Test Slack notification with sample data"""
    logger.info("=== TESTING SLACK NOTIFICATIONS ===")
    
    if not os.environ.get('SLACK_WEBHOOK_URL'):
        logger.info("Slack webhook not configured - skipping test")
        return True
    
    try:
        # Create test notification
        test_group = {
            'issue_type': 'Test Alert - Login Issues',
            'tickets': [
                {'id': '12345', 'subject': 'Cannot login to portal'},
                {'id': '12346', 'subject': 'Login page not loading'},
                {'id': '12347', 'subject': 'Password reset not working'},
                {'id': '12348', 'subject': 'Login timeout error'},
                {'id': '12349', 'subject': 'Account locked after login'}
            ]
        }
        
        logger.info("Sending test Slack notification...")
        success = send_slack_notification(test_group)
        
        if success:
            logger.info("✓ Test Slack notification sent successfully")
            return True
        else:
            logger.error("✗ Test Slack notification failed")
            return False
            
    except Exception as e:
        logger.error(f"✗ Slack test failed: {e}")
        return False

def print_all_ticket_fields():
    """Fetch and print all ticket field definitions from Zendesk"""
    logger.info("=== FETCHING ALL ZENDESK TICKET FIELDS ===")
    try:
        # Use environment variables for auth
        zendesk_url = os.environ.get('ZENDESK_URL')
        zendesk_email = os.environ.get('ZENDESK_EMAIL')
        zendesk_token = os.environ.get('ZENDESK_TOKEN')
        if not (zendesk_url and zendesk_email and zendesk_token):
            logger.error("Missing Zendesk credentials in environment variables.")
            return False
        
        api_url = f"{zendesk_url.rstrip('/')}/api/v2/ticket_fields.json"
        auth = (f"{zendesk_email}/token", zendesk_token)
        resp = requests.get(api_url, auth=auth)
        if resp.status_code != 200:
            logger.error(f"Failed to fetch ticket fields: {resp.status_code} {resp.text}")
            return False
        data = resp.json()
        fields = data.get('ticket_fields', [])
        logger.info(f"Found {len(fields)} ticket fields:")
        for field in fields:
            logger.info(f"  ID: {field.get('id')}, Type: {field.get('type')}, Title: {field.get('title')}, Key: {field.get('key')}")
        return True
    except Exception as e:
        logger.error(f"Error fetching ticket fields: {e}")
        return False

def run_all_tests():
    """Run all tests in sequence"""
    logger.info("🧪 RUNNING ALL TESTS")
    print("=" * 50)
    
    tests = [
        ("Environment", test_environment),
        ("Zendesk API", test_zendesk),
        ("Ticket Analysis", test_analysis),
        ("Slack Notifications", test_slack)
    ]
    
    results = []
    for name, test_func in tests:
        success = test_func()
        results.append((name, success))
        print()
    
    # Summary
    logger.info("🏁 TEST SUMMARY")
    all_passed = True
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"  {name}: {status}")
        if not success:
            all_passed = False
    
    if all_passed:
        logger.info("🎉 All tests passed! System is ready to use.")
    else:
        logger.error("❌ Some tests failed. Check configuration and try again.")

def show_help():
    """Show usage instructions"""
    print("""
🧪 Zendesk Alert System - Testing Tool

Usage:
    python debug_checker.py [command]

Commands:
    env          Test environment variables
    zendesk      Test Zendesk API connection
    analysis     Test ticket analysis with sample data
    slack        Test Slack notifications
    fields       Fetch and print all Zendesk ticket field definitions
    all          Run all tests (default)
    help         Show this help message
    query        Run a custom query/analysis and send summary to Slack

Environment Variables:
    SEND_TEST_SLACK=true    Enable Slack notification testing
    
Examples:
    python debug_checker.py                    # Run all tests
    python debug_checker.py zendesk           # Test only Zendesk API
    SEND_TEST_SLACK=true python debug_checker.py slack  # Test Slack notifications
    python debug_checker.py query "How many login related tickets do we have?"  # Custom query
    """)

if __name__ == "__main__":
    # Parse command line arguments
    command = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if command == "help":
        show_help()
    elif command == "env":
        test_environment()
    elif command == "zendesk":
        test_zendesk()
    elif command == "analysis":
        test_analysis()
    elif command == "slack":
        test_slack()
    elif command == "fields":
        print_all_ticket_fields()
    elif command == "all":
        run_all_tests()
    elif command == "query":
        if len(sys.argv) < 3:
            logger.error("No query provided. Usage: python debug_checker.py query 'your question here'")
            sys.exit(1)
        custom_query = " ".join(sys.argv[2:])
        logger.info(f"Running custom query: {custom_query}")
        tickets = fetch_recent_tickets()
        parsed_data, summary = analyze_tickets_with_query(tickets, custom_query)
        print("\n=== QUERY SUMMARY ===\n" + summary)
        
        # Extract tickets from unified format
        slack_tickets = []
        if parsed_data and isinstance(parsed_data, dict):
            response_type = parsed_data.get('response_type', 'unknown')
            logger.info(f"Response type: {response_type}")
            
            data = parsed_data.get('data', {})
            logger.info(f"Data section: {data}")
            
            if isinstance(data, dict):
                slack_tickets = data.get('tickets', [])
                logger.info(f"Extracted {len(slack_tickets)} tickets from unified format")
                logger.info(f"Tickets: {slack_tickets}")
        
        # Send to Slack with unified format
        slack_payload = {
            "issue_type": f"Custom Query: {custom_query}",
            "tickets": slack_tickets,
            "summary": summary,
            "parsed_data": parsed_data
        }
        
        if send_slack_notification(slack_payload):
            logger.info("✓ Custom query summary sent to Slack")
        else:
            logger.error("✗ Failed to send custom query summary to Slack")
    else:
        logger.error(f"Unknown command: {command}")
        show_help()
        sys.exit(1) 