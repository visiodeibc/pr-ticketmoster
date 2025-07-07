import os
import logging
from datetime import datetime, timedelta, timezone
from zenpy import Zenpy
from dotenv import load_dotenv
from constants import CUSTOM_FIELD_MAP, TICKET_FETCH_HOURS

load_dotenv()

# Configure logging
logger = logging.getLogger('zendesk_client')

# Product tag mapping
PRODUCT_TAGS = {
    'web_portal': 'WebPortal', 'webportal': 'WebPortal',
    'mobile_app': 'MobileApp', 'mobile': 'MobileApp',
    'reporting': 'ReportingTool', 'reports': 'ReportingTool',
    'dashboard': 'Dashboard', 'billing': 'Billing', 'api': 'API'
}

class ZendeskClient:
    def __init__(self):
        """Initialize Zendesk client with credentials from environment variables"""
        self.zendesk_url = os.environ.get('ZENDESK_URL')
        self.zendesk_email = os.environ.get('ZENDESK_EMAIL')
        self.zendesk_token = os.environ.get('ZENDESK_TOKEN')
        
        if not all([self.zendesk_url, self.zendesk_email, self.zendesk_token]):
            logger.error("Missing Zendesk credentials: ZENDESK_URL, ZENDESK_EMAIL, ZENDESK_TOKEN")
            self.client = None
            return
            
        if not (self.zendesk_url.startswith('http://') or self.zendesk_url.startswith('https://')):
            logger.error(f"Invalid ZENDESK_URL format: {self.zendesk_url}")
            self.client = None
            return
        
        try:
            domain = self._extract_subdomain()
            if not domain:
                raise ValueError(f"Could not extract subdomain from URL: {self.zendesk_url}")
            
            self.client = Zenpy(subdomain=domain, email=self.zendesk_email, token=self.zendesk_token)
            logger.info("Successfully initialized Zendesk client")
            
            # Test connection
            try:
                user = self.client.users.me()
                logger.info(f"✓ Connected to Zendesk as: {user.email}")
            except Exception as test_e:
                logger.warning(f"Client initialized but connection test failed: {test_e}")
                
        except Exception as e:
            logger.error(f"Failed to initialize Zendesk client: {e}")
            self.client = None

    def _extract_subdomain(self):
        """Extract subdomain from Zendesk URL"""
        clean_url = self.zendesk_url.replace('https://', '').replace('http://', '').rstrip('/')
        logger.info(f"Processing Zendesk URL: {clean_url}")
        
        if '.zendesk.' in clean_url:
            domain = clean_url.split('.zendesk.')[0]
        else:
            domain = clean_url.split('.')[0]
        
        logger.info(f"Extracted Zendesk subdomain: '{domain}'")
        return domain if domain and domain != clean_url else None

    def fetch_tickets_last_24h(self):
        """Fetch tickets created in the last 24 hours from Zendesk"""
        return self.fetch_tickets_by_hours(TICKET_FETCH_HOURS)
    
    def fetch_tickets_by_hours(self, hours=None):
        """Fetch tickets created in the last N hours from Zendesk"""
        if not self.client:
            logger.error("Zendesk client not initialized. Cannot fetch tickets.")
            return []
        
        hours = hours or TICKET_FETCH_HOURS
        
        try:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=hours)
            
            logger.info(f"Fetching tickets created after {cutoff.isoformat()} ({hours} hours ago)")
            
            search_query = f"created>{cutoff.strftime('%Y-%m-%d')} type:ticket"
            logger.info(f"Zendesk search query: {search_query}")
            
            tickets = []
            for ticket in self.client.search(query=search_query, type='ticket'):
                if self._is_ticket_in_timeframe(ticket, cutoff):
                    ticket_data = self._convert_ticket_format(ticket)
                    tickets.append(ticket_data)
                    logger.debug(f"✓ Added ticket #{ticket.id}: {ticket.subject}")
            
            logger.info(f"Fetched {len(tickets)} tickets from Zendesk (last {hours} hours)")
            return tickets
            
        except Exception as e:
            logger.error(f"Error fetching tickets from Zendesk: {e}")
            return []

    def _is_ticket_in_timeframe(self, ticket, cutoff):
        """Check if ticket is within the specified timeframe"""
        if not hasattr(ticket, 'created_at') or not ticket.created_at:
            logger.warning(f"Ticket #{ticket.id} has no creation date")
            return True  # Include tickets without dates
        
        try:
            ticket_date = self._parse_ticket_date(ticket.created_at)
            logger.debug(f"Ticket #{ticket.id} created at {ticket_date.isoformat()}")
            
            if ticket_date >= cutoff:
                return True
            else:
                logger.debug(f"Skipping older ticket #{ticket.id} ({ticket_date.isoformat()})")
                return False
                
        except Exception as date_e:
            logger.error(f"Error processing date for ticket #{ticket.id}: {date_e}")
            logger.debug(f"Raw created_at value: {ticket.created_at}, type: {type(ticket.created_at)}")
            return True  # Include tickets with date parsing issues

    def _parse_ticket_date(self, created_at):
        """Parse ticket creation date to timezone-aware datetime"""
        if isinstance(created_at, str):
            return datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        elif hasattr(created_at, 'tzinfo') and created_at.tzinfo is None:
            return created_at.replace(tzinfo=timezone.utc)
        return created_at
    
    def _convert_ticket_format(self, zendesk_ticket):
        """Convert Zendesk ticket object to our expected format"""
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
        
        # Extract custom fields
        custom_field_values = self._extract_custom_fields(zendesk_ticket)
        
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

    def _extract_custom_fields(self, zendesk_ticket):
        """Extract custom fields from Zendesk ticket"""
        custom_field_values = {v: None for v in CUSTOM_FIELD_MAP.values()}
        
        if hasattr(zendesk_ticket, 'custom_fields') and zendesk_ticket.custom_fields:
            for field in zendesk_ticket.custom_fields:
                if field['id'] in CUSTOM_FIELD_MAP:
                    key = CUSTOM_FIELD_MAP[field['id']]
                    custom_field_values[key] = field.get('value')
        
        logger.debug(f"Extracted custom fields for ticket #{zendesk_ticket.id}: {custom_field_values}")
        return custom_field_values
    
    def _extract_product_from_tags(self, tags):
        """Extract product information from ticket tags"""
        for tag in tags:
            if tag.lower() in PRODUCT_TAGS:
                return PRODUCT_TAGS[tag.lower()]
        return 'Unknown'

# Initialize global client instance
zendesk_client = ZendeskClient()

def fetch_recent_tickets():
    """Fetch recent tickets from Zendesk (last 24 hours)"""
    return zendesk_client.fetch_tickets_last_24h()

def fetch_recent_tickets_by_hours(hours=None):
    """Fetch recent tickets from Zendesk with custom time window"""
    return zendesk_client.fetch_tickets_by_hours(hours)

 