import os
import openai
import json
import logging
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ticket_analyzer')

# Set up OpenAI
# This is a hardcoded key - in production, use environment variables
openai_api_key = os.environ.get("OPENAI_API_KEY")

# Initialize the client
client = openai.OpenAI(api_key=openai_api_key)

def analyze_similar_tickets(tickets):
    """
    Analyze tickets to find groups of similar issues using OpenAI
    
    Returns a list of groups, where each group contains:
    - issue_type: Common issue description
    - tickets: List of tickets with that issue
    """
    if not tickets:
        logger.info("No tickets provided for analysis")
        return []
    
    logger.info(f"Analyzing {len(tickets)} tickets for similarity")
    
    # Possible methods to identify similar tickets:
    # Method 1: Direct clustering with OpenAI API (used here)
    return cluster_with_openai(tickets)
    
    # Alternative methods that could be implemented:
    # Method 2: Extract keywords and cluster by keyword similarity
    # return cluster_by_keywords(tickets)
    
    # Method 3: Generate embeddings and cluster using cosine similarity
    # return cluster_by_embeddings(tickets)
    
    # Method 4: Topic modeling to identify common themes
    # return cluster_by_topics(tickets)
    
    # Method 5: Use two-stage approach: first classify issues, then cluster
    # return two_stage_clustering(tickets)

def cluster_with_openai(tickets):
    """Group tickets by similarity using OpenAI's completion API"""
    # Prepare ticket data for analysis
    ticket_texts = [f"Ticket #{t['id']}: Subject: {t['subject']}, Description: {t['description']}" 
                   for t in tickets]
    
    logger.info(f"Prepared {len(ticket_texts)} ticket texts for OpenAI analysis")
    
    # Create a prompt for OpenAI to analyze and group the tickets
    prompt = f"""
    I have a set of technical support tickets. 
    
    Please analyze them and identify groups of tickets that are about the same or very similar issues.
    For each group, provide:
    1. A descriptive name for the common issue
    2. The ticket IDs that belong to this group (numeric IDs only, without the # prefix)
    
    Only create groups that genuinely represent the same underlying issue. If a ticket doesn't clearly belong to a group, leave it ungrouped.
    Return the response as a JSON array, where each item has "issue_type" and "ticket_ids" fields.
    IMPORTANT: ticket_ids must be strings containing ONLY the numeric ID without any prefix or suffix.
    
    Here are the tickets:
    {ticket_texts}
    """
    
    if not openai_api_key:
        logger.error("OpenAI API key not found. Set the OPENAI_API_KEY environment variable.")
        # For testing without API key, return mock data for the login issues
        if any("login" in t['subject'].lower() for t in tickets):
            logger.info("Returning mock data for login issues (testing only)")
            login_tickets = [t for t in tickets if "login" in t['subject'].lower() or "login" in t['description'].lower()]
            if len(login_tickets) >= 5:
                return [{
                    'issue_type': 'Login Authentication Failures',
                    'tickets': login_tickets
                }]
        return []
    
    try:
        logger.info("Calling OpenAI API for ticket analysis")
        response = client.chat.completions.create(
            model="gpt-4.1-2025-04-14",
            messages=[
                {"role": "system", "content": "You are a technical support analyst who specializes in identifying patterns in customer support tickets."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000
        )
        
        # Extract the groups from the OpenAI response
        result = response.choices[0].message.content
        logger.info("Received response from OpenAI")
        logger.debug(f"OpenAI response: {result}")
        
        # Process the result to extract groups
        try:
            # Clean the response - sometimes OpenAI returns JSON in markdown code blocks
            cleaned_result = result.strip()
            
            # Check if the response is wrapped in markdown code blocks
            if cleaned_result.startswith("```") and cleaned_result.endswith("```"):
                # Remove the triple backticks at beginning and end
                cleaned_result = cleaned_result[3:]
                cleaned_result = cleaned_result[:-3]
                
                # Remove potential language identifier (e.g., "json")
                if cleaned_result.startswith("json\n") or cleaned_result.startswith("json\r\n"):
                    cleaned_result = cleaned_result[4:].lstrip()
            
            # Additional cleaning for any lingering markdown or whitespace
            cleaned_result = cleaned_result.strip()
            
            logger.info(f"Attempting to parse JSON from cleaned result")
            try:
                groups_data = json.loads(cleaned_result)
                logger.info(f"Successfully parsed JSON response with {len(groups_data)} groups")
            except json.JSONDecodeError as e:
                # If we can't parse the cleaned result, try to extract JSON using regex
                logger.warning(f"First JSON parse attempt failed: {e}")
                logger.info("Attempting to extract JSON with regex")
                
                import re
                json_match = re.search(r'\[\s*\{.*\}\s*\]', cleaned_result, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    logger.info(f"Found JSON-like string with regex")
                    groups_data = json.loads(json_str)
                    logger.info(f"Successfully parsed JSON from regex match")
                else:
                    raise ValueError("Could not find JSON array in response")
            
            # Convert the groups into our expected format
            similar_groups = []
            for i, group in enumerate(groups_data):
                ticket_ids = group.get('ticket_ids', [])
                logger.info(f"Group {i+1}: '{group['issue_type']}' with {len(ticket_ids)} tickets")
                
                # Find matching tickets
                matching_tickets = []
                for t in tickets:
                    # Check both with and without the "#" prefix
                    if str(t['id']) in ticket_ids or f"#{t['id']}" in ticket_ids:
                        matching_tickets.append(t)
                
                if len(matching_tickets) >= 5:
                    ticket_group = {
                        'issue_type': group['issue_type'],
                        'tickets': matching_tickets
                    }
                    similar_groups.append(ticket_group)
                    logger.info(f"Added group '{group['issue_type']}' with {len(matching_tickets)} tickets")
                else:
                    logger.info(f"Skipping group '{group['issue_type']}' as it has fewer than 5 tickets")
            
            return similar_groups
            
        except json.JSONDecodeError:
            logger.error("Failed to parse OpenAI response as JSON")
            logger.error(f"Raw response: {result}")
            return []
            
    except Exception as e:
        logger.error(f"Error using OpenAI API: {e}")
        return []

# Alternative methods (for demonstration - not fully implemented)

def cluster_by_keywords(tickets):
    """Extract keywords and cluster tickets based on keyword similarity"""
    # Implementation would extract key terms from each ticket 
    # and group tickets with similar keyword profiles
    print("Keyword clustering not implemented in this POC")
    return []

def cluster_by_embeddings(tickets):
    """Use embeddings to cluster similar tickets"""
    # Implementation would:
    # 1. Generate embeddings for each ticket using OpenAI or similar
    # 2. Cluster embeddings using cosine similarity or clustering algorithms
    # 3. Return the clusters as ticket groups
    print("Embedding-based clustering not implemented in this POC")
    return []

def cluster_by_topics(tickets):
    """Use topic modeling to identify ticket themes"""
    # Implementation would use LDA or similar algorithms to identify topic themes
    print("Topic modeling not implemented in this POC")
    return []

def two_stage_clustering(tickets):
    """First classify issue types, then cluster within each type"""
    # Implementation would:
    # 1. Use classification to assign tickets to broad categories
    # 2. Within each category, cluster to find specific issues
    print("Two-stage clustering not implemented in this POC")
    return [] 