import os
import json
import logging
from datetime import datetime, timedelta, timezone
from zenpy import Zenpy
from zenpy.lib.api_objects import Ticket
from dotenv import load_dotenv
from constants import CUSTOM_FIELD_MAP, TICKET_FETCH_HOURS

load_dotenv()

# Configure logging
logger = logging.getLogger('zendesk_client')

class ZendeskClient:
    def __init__(self):
        """Initialize Zendesk client with credentials from environment variables"""
        self.zendesk_url = os.environ.get('ZENDESK_URL')  # e.g., 'https://yourcompany.zendesk.com'
        self.zendesk_email = os.environ.get('ZENDESK_EMAIL')  # Your Zendesk email
        self.zendesk_token = os.environ.get('ZENDESK_TOKEN')  # Your API token
        
        if not all([self.zendesk_url, self.zendesk_email, self.zendesk_token]):
            logger.error("Missing Zendesk credentials. Please set ZENDESK_URL, ZENDESK_EMAIL, and ZENDESK_TOKEN environment variables.")
            logger.error("Example values:")
            logger.error("  ZENDESK_URL=https://yourcompany.zendesk.com")
            logger.error("  ZENDESK_EMAIL=your-email@company.com")
            logger.error("  ZENDESK_TOKEN=your_api_token_here")
            self.client = None
            return
            
        # Validate URL format
        if not (self.zendesk_url.startswith('http://') or self.zendesk_url.startswith('https://')):
            logger.error(f"Invalid ZENDESK_URL format: {self.zendesk_url}")
            logger.error("URL should start with https:// (e.g., https://yourcompany.zendesk.com)")
            self.client = None
            return
        
        try:
            # Extract subdomain from URL more robustly
            # Remove protocol and trailing slashes
            clean_url = self.zendesk_url.replace('https://', '').replace('http://', '').rstrip('/')
            logger.info(f"Processing Zendesk URL: {clean_url}")
            
            # Extract subdomain (everything before .zendesk.*)
            if '.zendesk.' in clean_url:
                domain = clean_url.split('.zendesk.')[0]
            else:
                # If URL doesn't contain .zendesk., assume it's just the subdomain
                domain = clean_url.split('.')[0]
            
            logger.info(f"Extracted Zendesk subdomain: '{domain}'")
            
            if not domain or domain == clean_url:
                raise ValueError(f"Could not extract valid subdomain from URL: {self.zendesk_url}. Expected format: https://yourcompany.zendesk.com")
            
            # Initialize Zenpy client
            self.client = Zenpy(
                subdomain=domain,  # Use 'subdomain' parameter instead of 'domain'
                email=self.zendesk_email,
                token=self.zendesk_token
            )
            logger.info("Successfully initialized Zendesk client")
            
            # Test connection by making a simple API call
            try:
                # Try to get user info to verify connection
                user = self.client.users.me()
                logger.info(f"✓ Connected to Zendesk as: {user.email}")
            except Exception as test_e:
                logger.warning(f"Client initialized but connection test failed: {test_e}")
                
        except Exception as e:
            logger.error(f"Failed to initialize Zendesk client: {e}")
            logger.error(f"Make sure your ZENDESK_URL is in the format: https://yourcompany.zendesk.com")
            self.client = None

    def fetch_tickets_last_24h(self):
        """
        Fetch tickets created in the last 24 hours from Zendesk
        
        Returns:
            list: List of ticket dictionaries in our expected format
        """
        if not self.client:
            logger.error("Zendesk client not initialized. Cannot fetch tickets.")
            return []
        
        try:
            # Calculate hours ago based on constant
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=TICKET_FETCH_HOURS)
            
            logger.info(f"Fetching tickets created after {cutoff.isoformat()}")
            
            # Use Zendesk search API to get tickets from last period
            # Format: created>YYYY-MM-DD type:ticket
            search_query = f"created>{cutoff.strftime('%Y-%m-%d')} type:ticket"
            
            logger.info(f"Zendesk search query: {search_query}")
            
            # Fetch tickets using search
            tickets = []
            for ticket in self.client.search(query=search_query, type='ticket'):
                # Convert ticket creation time to timezone-aware datetime
                
                if hasattr(ticket, 'created_at') and ticket.created_at:
                    try:
                        ticket_date = ticket.created_at
                        
                        # Handle different date formats from Zendesk
                        if isinstance(ticket_date, str):
                            # Parse ISO format string
                            ticket_date = datetime.fromisoformat(ticket_date.replace('Z', '+00:00'))
                        elif hasattr(ticket_date, 'tzinfo') and ticket_date.tzinfo is None:
                            # Add UTC timezone if missing
                            ticket_date = ticket_date.replace(tzinfo=timezone.utc)
                        
                        logger.debug(f"Ticket #{ticket.id} created at {ticket_date.isoformat()}")
                        
                        # Only include tickets from the last period
                        if ticket_date >= cutoff:
                            ticket_data = self._convert_ticket_format(ticket)
                            tickets.append(ticket_data)
                            logger.debug(f"✓ Added ticket #{ticket.id}: {ticket.subject}")
                        else:
                            logger.debug(f"Skipping older ticket #{ticket.id} ({ticket_date.isoformat()})")
                    except Exception as date_e:
                        logger.error(f"Error processing date for ticket #{ticket.id}: {date_e}")
                        logger.debug(f"Raw created_at value: {ticket.created_at}, type: {type(ticket.created_at)}")
                        # Still add the ticket but log the issue
                        ticket_data = self._convert_ticket_format(ticket)
                        tickets.append(ticket_data)
                else:
                    logger.warning(f"Ticket #{ticket.id} has no creation date")
            
            logger.info(f"Fetched {len(tickets)} tickets from Zendesk")
            return tickets
            
        except Exception as e:
            logger.error(f"Error fetching tickets from Zendesk: {e}")
            return []
    
    def _convert_ticket_format(self, zendesk_ticket):
        """
        Convert Zendesk ticket object to our expected format
        
        Args:
            zendesk_ticket: Zenpy ticket object
            
        Returns:
            dict: Ticket in our expected format
        """
        # Handle created_at date conversion
        created_at_iso = None
        if zendesk_ticket.created_at:
            try:
                if isinstance(zendesk_ticket.created_at, str):
                    created_at_iso = zendesk_ticket.created_at
                else:
                    created_at_iso = zendesk_ticket.created_at.isoformat()
            except Exception as e:
                logger.warning(f"Could not convert created_at for ticket #{zendesk_ticket.id}: {e}")
                created_at_iso = str(zendesk_ticket.created_at)
        
        # Extract custom fields by ID
        custom_field_map = CUSTOM_FIELD_MAP
        custom_field_values = {v: None for v in custom_field_map.values()}
        if hasattr(zendesk_ticket, 'custom_fields') and zendesk_ticket.custom_fields:
            for field in zendesk_ticket.custom_fields:
                if field['id'] in custom_field_map:
                    key = custom_field_map[field['id']]
                    custom_field_values[key] = field.get('value')
        # Optionally log extracted custom fields
        logger.debug(f"Extracted custom fields for ticket #{zendesk_ticket.id}: {custom_field_values}")
        
        return {
            'id': zendesk_ticket.id,
            'subject': zendesk_ticket.subject or 'No subject',
            'description': zendesk_ticket.description or 'No description',
            'created_at': created_at_iso,
            'status': zendesk_ticket.status,
            'priority': zendesk_ticket.priority,
            'customer_id': str(zendesk_ticket.requester_id) if zendesk_ticket.requester_id else None,
            'product': self._extract_product_from_tags(zendesk_ticket.tags) if zendesk_ticket.tags else 'Unknown',
            **custom_field_values
        }
    
    def _extract_product_from_tags(self, tags):
        """
        Extract product information from ticket tags
        
        Args:
            tags: List of ticket tags
            
        Returns:
            str: Product name or 'Unknown'
        """
        # Common product tags - customize based on your Zendesk setup
        product_tags = {
            'web_portal': 'WebPortal',
            'webportal': 'WebPortal',
            'mobile_app': 'MobileApp',
            'mobile': 'MobileApp',
            'reporting': 'ReportingTool',
            'reports': 'ReportingTool',
            'dashboard': 'Dashboard',
            'billing': 'Billing',
            'api': 'API'
        }
        
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower in product_tags:
                return product_tags[tag_lower]
        
        return 'Unknown'

# Initialize global client instance
zendesk_client = ZendeskClient()

def fetch_recent_tickets():
    """
    Public function to fetch recent tickets from Zendesk
    
    Returns:
        list: List of tickets from the last 24 hours
    """
    return zendesk_client.fetch_tickets_last_24h()

def save_tickets_locally(tickets, filename='fetched_tickets.json'):
    """
    Save fetched tickets to local file for backup and debugging
    
    Args:
        tickets: List of ticket dictionaries
        filename: Name of file to save to
    """
    try:
        with open(filename, 'w') as f:
            json.dump(tickets, f, indent=2, default=str)
        logger.info(f"Saved {len(tickets)} tickets to {filename}")
    except Exception as e:
        logger.error(f"Failed to save tickets to {filename}: {e}")

def load_tickets_from_file(filename='fetched_tickets.json'):
    """
    Load tickets from local file as fallback
    
    Args:
        filename: Name of file to load from
        
    Returns:
        list: List of tickets or empty list if file doesn't exist
    """
    try:
        with open(filename, 'r') as f:
            tickets = json.load(f)
        logger.info(f"Loaded {len(tickets)} tickets from {filename}")
        return tickets
    except FileNotFoundError:
        logger.warning(f"File {filename} not found")
        return []
    except Exception as e:
        logger.error(f"Failed to load tickets from {filename}: {e}")
        return [] 