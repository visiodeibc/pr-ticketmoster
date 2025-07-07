import os
import openai
import json
import logging
from collections import defaultdict
from dotenv import load_dotenv
from constants import (
    OPENAI_CLUSTERING_FORMAT, 
    OPENAI_QUERY_FORMAT,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_TOKENS_CLUSTERING,
    OPENAI_MAX_TOKENS_QUERY,
    MIN_TICKETS_FOR_GROUP,
    SYSTEM_MESSAGE
)
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

def parse_openai_response(response_text, expected_type="unknown"):
    """
    Parse OpenAI response with unified error handling and logging.
    Returns (parsed_data, success) tuple.
    """
    try:
        # Remove markdown/code block if present
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            # Remove all leading/trailing backticks and whitespace
            cleaned = cleaned.strip('`').strip()
            # Remove language identifier if present
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].lstrip('\n').lstrip()
        
        logger.info(f"Cleaned OpenAI response for JSON parsing: {cleaned[:200]}...")
        parsed = json.loads(cleaned)
        logger.info(f"Successfully parsed {expected_type} response")
        return parsed, True
    except Exception as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {e}")
        logger.error(f"Raw response: {response_text[:200]}...")
        return None, False

def cluster_with_openai(tickets):
    """Group tickets by similarity using OpenAI's completion API"""
    # Prepare ticket data for analysis
    ticket_texts = [
        f"Ticket #{t['id']}: Subject: {t['subject']}, Description: {t['description']}, "
        f"Internal Chart/Tool: {t.get('internal_chart_tool', '')}, "
        f"Internal Chart/Tool - AI tagged: {t.get('internal_chart_tool_ai_tagged', '')}, "
        f"Internal Chart/Tool - AI generated: {t.get('internal_chart_tool_ai_generated', '')}, "
        f"Steps to reproduce: {t.get('steps_to_reproduce', '')}, "
        f"Request Type - AI tagged: {t.get('request_type_ai_tagged', '')}, "
        f"Request Type - CNIL: {t.get('request_type_cnil', '')}, "
        f"Requester Type: {t.get('requester_type', '')}, "
        f"JIRA ID: {t.get('jira_id', '')}, "
        f"JIRA Ticket ID: {t.get('jira_ticket_id', '')}, "
        f"Link to Discourse: {t.get('link_to_discourse', '')}"
        for t in tickets
    ]
    
    logger.info(f"Prepared {len(ticket_texts)} ticket texts for OpenAI analysis")
    
    # Create a prompt for OpenAI to analyze and group the tickets
    prompt = f"""
    I have a set of technical support tickets. 
    
    Please analyze them and identify groups of tickets that are about the same or very similar issues.
    
    Return your response as a JSON object with this exact structure:
    {OPENAI_CLUSTERING_FORMAT.format(total_tickets=len(tickets))}
    
    IMPORTANT: 
    - Only create groups with {MIN_TICKETS_FOR_GROUP}+ tickets that genuinely represent the same underlying issue
    - ticket_ids must be strings containing ONLY the numeric ID without any prefix or suffix
    - Update groups_found to the actual number of groups returned
    
    Here are the tickets:
    {ticket_texts}
    """
    
    if not openai_api_key:
        logger.error("OpenAI API key not found. Set the OPENAI_API_KEY environment variable.")
        return []
    
    try:
        logger.info("Calling OpenAI API for ticket clustering")
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ],
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS_CLUSTERING
        )
        
        result = response.choices[0].message.content
        logger.info("Received response from OpenAI")
        
        # Parse using unified parser
        parsed_data, success = parse_openai_response(result, "clustering")
        if not success:
            return []
        
        # Extract groups and convert to legacy format
        groups = parsed_data.get("data", {}).get("groups", [])
        similar_groups = []
        
        for group in groups:
            ticket_ids = group.get('ticket_ids', [])
            logger.info(f"Processing group '{group.get('issue_type')}' with {len(ticket_ids)} tickets")
            
            # Find matching tickets
            matching_tickets = []
            for t in tickets:
                if str(t['id']) in ticket_ids:
                    matching_tickets.append(t)
            
            if len(matching_tickets) >= MIN_TICKETS_FOR_GROUP:
                ticket_group = {
                    'issue_type': group.get('issue_type'),
                    'tickets': matching_tickets
                }
                similar_groups.append(ticket_group)
                logger.info(f"Added group '{group.get('issue_type')}' with {len(matching_tickets)} tickets")
            else:
                logger.info(f"Skipping group '{group.get('issue_type')}' as it has fewer than {MIN_TICKETS_FOR_GROUP} tickets")
        
        return similar_groups
        
    except Exception as e:
        logger.error(f"Error using OpenAI API: {e}")
        return []

def analyze_tickets_with_query(tickets, query):
    """
    Analyze tickets with a custom query using OpenAI.
    Returns a tuple: (parsed_data, slack_summary)
    """
    if not tickets:
        logger.info("No tickets provided for analysis with query")
        return None, "No tickets to analyze."
    if not query:
        logger.info("No query provided for analysis.")
        return None, "No query provided."
    logger.info(f"Analyzing {len(tickets)} tickets with custom query: {query}")

    ticket_texts = [
        f"Ticket #{t['id']}: Subject: {t['subject']}, Description: {t['description']}, "
        f"Internal Chart/Tool: {t.get('internal_chart_tool', '')}, "
        f"Internal Chart/Tool - AI tagged: {t.get('internal_chart_tool_ai_tagged', '')}, "
        f"Internal Chart/Tool - AI generated: {t.get('internal_chart_tool_ai_generated', '')}, "
        f"Steps to reproduce: {t.get('steps_to_reproduce', '')}, "
        f"Request Type - AI tagged: {t.get('request_type_ai_tagged', '')}, "
        f"Request Type - CNIL: {t.get('request_type_cnil', '')}, "
        f"Requester Type: {t.get('requester_type', '')}, "
        f"JIRA ID: {t.get('jira_id', '')}, "
        f"JIRA Ticket ID: {t.get('jira_ticket_id', '')}, "
        f"Link to Discourse: {t.get('link_to_discourse', '')}"
        for t in tickets
    ]
    
    prompt = f"""
    You are a technical support analyst. Here is a list of support tickets:
    {ticket_texts}

    Please answer the following question based on the tickets above:
    {query}

    Return your response as a JSON object with this exact structure:
    {OPENAI_QUERY_FORMAT.format(total_tickets=len(tickets), query=query)}
    
    IMPORTANT: 
    - Include relevant tickets in the tickets array
    - Update count to reflect the actual number of relevant tickets
    - Make summary concise but informative
    """
    
    if not openai_api_key:
        logger.error("OpenAI API key not found.")
        return None, "OpenAI API key not configured."
    
    try:
        logger.info("Calling OpenAI API for custom query analysis")
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ],
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS_QUERY
        )
        
        result = response.choices[0].message.content.strip()
        logger.info("Received response from OpenAI for custom query")
        
        # Parse using unified parser
        parsed_data, success = parse_openai_response(result, "query")
        if not success:
            return None, result
        
        summary = parsed_data.get("summary", "No summary available")
        logger.info(f"Parsed query response successfully. Summary: {summary}")
        
        return parsed_data, summary
        
    except Exception as e:
        logger.error(f"Error using OpenAI API for custom query: {e}")
        return None, f"Error analyzing tickets: {e}"

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