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
    SYSTEM_MESSAGE,
    OPENAI_TIME_WINDOW_FORMAT,
    MAX_LOOKBACK_HOURS,
    DEFAULT_QUERY_HOURS,
    LARGE_RESULT_THRESHOLD
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
    This function is now deprecated in favor of analyze_tickets_with_query_and_timeframe.
    Returns a tuple: (parsed_data, slack_summary)
    """
    return analyze_tickets_with_query_and_timeframe(tickets, query)

def analyze_tickets_with_query_and_timeframe(tickets, query, custom_timeframe=None):
    """
    Analyze tickets with a custom query using OpenAI, with support for dynamic time windows.
    
    Args:
        tickets (list): List of tickets to analyze (will be ignored if custom_timeframe is provided)
        query (str): User's query
        custom_timeframe (dict, optional): Custom time window information. If None, will extract from query.
    
    Returns:
        tuple: (parsed_data, slack_summary, time_window_info)
    """
    if not query:
        logger.info("No query provided for analysis.")
        return None, "No query provided.", None
    
    # Extract time window from query if not provided
    if custom_timeframe is None:
        time_window_info = extract_time_window_from_query(query)
    else:
        time_window_info = custom_timeframe
    
    logger.info(f"Using time window: {time_window_info}")
    
    # Fetch tickets based on the time window
    from zendesk_client import fetch_recent_tickets_by_hours
    
    if time_window_info.get("has_time_reference", False) or custom_timeframe is not None:
        hours = time_window_info.get("hours", DEFAULT_QUERY_HOURS)
        logger.info(f"Fetching tickets from last {hours} hours based on query time reference")
        tickets = fetch_recent_tickets_by_hours(hours)
    else:
        # Use provided tickets or fetch default
        if not tickets:
            logger.info("No tickets provided and no time reference found, fetching default tickets")
            tickets = fetch_recent_tickets_by_hours(DEFAULT_QUERY_HOURS)
    
    if not tickets:
        logger.info("No tickets found for analysis with query")
        return None, "No tickets found for the specified time window.", time_window_info
    
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
    
    # Include time window information in the prompt
    time_context = f"These tickets were collected from the {time_window_info.get('description', 'last 24 hours')}."
    
    prompt = f"""
    You are a technical support analyst. Here is a list of support tickets:
    {ticket_texts}

    {time_context}

    Please answer the following question based on the tickets above:
    {query}

    IMPORTANT INSTRUCTIONS:
    - If your analysis finds more than {LARGE_RESULT_THRESHOLD} relevant tickets, set "large_result_set" to true
    - For large result sets (>{LARGE_RESULT_THRESHOLD} tickets):
      * Only provide ticket IDs in the "ticket_ids" array (no detailed ticket objects)
      * Keep the "tickets" array empty
      * Focus on a concise summary
    - For smaller result sets (≤{LARGE_RESULT_THRESHOLD} tickets):
      * Set "large_result_set" to false
      * Include detailed ticket objects in the "tickets" array
      * Also include ticket IDs in the "ticket_ids" array
    - Always update "count" to reflect the actual number of relevant tickets found
    - In your summary, always use the ACTUAL COUNT of tickets found, not the threshold number ({LARGE_RESULT_THRESHOLD})
    - Make summary concise but informative
    - Consider the time window context in your analysis

    Return your response as a JSON object with this exact structure:
    {OPENAI_QUERY_FORMAT.format(total_tickets=len(tickets), query=query)}
    """
    
    if not openai_api_key:
        logger.error("OpenAI API key not found.")
        return None, "OpenAI API key not configured.", time_window_info
    
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
            return None, result, time_window_info
        
        # Add time window information to metadata
        if parsed_data and "metadata" in parsed_data:
            parsed_data["metadata"]["time_window"] = time_window_info
        
        summary = parsed_data.get("summary", "No summary available")
        
        # Enhance summary with time window context
        time_desc = time_window_info.get("description", "last 24 hours")
        enhanced_summary = f"{summary} (Data from {time_desc})"
        
        logger.info(f"Parsed query response successfully. Enhanced summary: {enhanced_summary}")
        
        return parsed_data, enhanced_summary, time_window_info
        
    except Exception as e:
        logger.error(f"Error using OpenAI API for custom query: {e}")
        return None, f"Error analyzing tickets: {e}", time_window_info

def extract_time_window_from_query(query):
    """
    Extract time window information from user query using OpenAI
    
    Args:
        query (str): User's query text
        
    Returns:
        dict: Time window information in format:
            {
                "has_time_reference": bool,
                "hours": int,
                "description": str,
                "reasoning": str
            }
    """
    if not query:
        logger.warning("No query provided for time window extraction")
        return {
            "has_time_reference": False,
            "hours": DEFAULT_QUERY_HOURS,
            "description": f"last {DEFAULT_QUERY_HOURS} hours",
            "reasoning": "No query provided"
        }
    
    logger.info(f"Extracting time window from query: {query}")
    
    prompt = f"""
    Analyze the following user query and determine if it contains any time references (like "last week", "yesterday", "past 3 days", "previous month", etc.).
    
    Query: "{query}"
    
    If there is a time reference, convert it to hours and provide a human-readable description.
    If there is no time reference, set has_time_reference to false and use the default.
    
    Maximum lookback allowed: {MAX_LOOKBACK_HOURS} hours ({MAX_LOOKBACK_HOURS // 24} days)
    Default time window: {DEFAULT_QUERY_HOURS} hours
    
    Common conversions:
    - "last hour" = 1 hour
    - "last 24 hours" / "yesterday" = 24 hours
    - "last 2 days" = 48 hours
    - "last week" = 168 hours (7 days)
    - "last month" = 720 hours (30 days)
    - "last 2 months" = 1440 hours (60 days)
    
    Return your response as a JSON object with this exact structure:
    {OPENAI_TIME_WINDOW_FORMAT}
    
    IMPORTANT: 
    - If the requested time window exceeds the maximum lookback ({MAX_LOOKBACK_HOURS} hours), cap it at the maximum
    - Be conservative with ambiguous time references
    - Provide clear reasoning for your decision
    """
    
    if not openai_api_key:
        logger.error("OpenAI API key not found for time window extraction")
        return {
            "has_time_reference": False,
            "hours": DEFAULT_QUERY_HOURS,
            "description": f"last {DEFAULT_QUERY_HOURS} hours",
            "reasoning": "OpenAI API key not available"
        }
    
    try:
        logger.info("Calling OpenAI API for time window extraction")
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert at understanding time references in natural language queries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Lower temperature for more consistent parsing
            max_tokens=1000
        )
        
        result = response.choices[0].message.content.strip()
        logger.info("Received time window extraction response from OpenAI")
        
        # Parse the JSON response
        try:
            parsed_result = json.loads(result)
            logger.info(f"Successfully parsed time window: {parsed_result}")
            
            # Extract and validate the time window information
            has_time_reference = parsed_result.get("has_time_reference", False)
            hours = parsed_result.get("time_window", {}).get("hours", DEFAULT_QUERY_HOURS)
            description = parsed_result.get("time_window", {}).get("description", f"last {hours} hours")
            reasoning = parsed_result.get("reasoning", "Extracted from query")
            
            # Ensure hours is within bounds
            if hours > MAX_LOOKBACK_HOURS:
                logger.warning(f"Time window {hours} hours exceeds maximum {MAX_LOOKBACK_HOURS} hours, capping it")
                hours = MAX_LOOKBACK_HOURS
                description = f"last {MAX_LOOKBACK_HOURS // 24} days (capped at maximum)"
                reasoning += f" (capped at maximum lookback of {MAX_LOOKBACK_HOURS} hours)"
            
            return {
                "has_time_reference": has_time_reference,
                "hours": hours,
                "description": description,
                "reasoning": reasoning
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse time window JSON response: {e}")
            logger.error(f"Raw response: {result}")
            return {
                "has_time_reference": False,
                "hours": DEFAULT_QUERY_HOURS,
                "description": f"last {DEFAULT_QUERY_HOURS} hours",
                "reasoning": f"Failed to parse OpenAI response: {e}"
            }
            
    except Exception as e:
        logger.error(f"Error extracting time window from query: {e}")
        return {
            "has_time_reference": False,
            "hours": DEFAULT_QUERY_HOURS,
            "description": f"last {DEFAULT_QUERY_HOURS} hours",
            "reasoning": f"Error calling OpenAI: {e}"
        }

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