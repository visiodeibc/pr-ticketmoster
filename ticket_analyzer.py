import os
import openai
import json
import logging
import re
from collections import defaultdict
from dotenv import load_dotenv
from constants import (
    OPENAI_CLUSTERING_FORMAT, OPENAI_QUERY_FORMAT, OPENAI_TIME_WINDOW_FORMAT,
    OPENAI_MODEL, OPENAI_TEMPERATURE, OPENAI_MAX_TOKENS_CLUSTERING, OPENAI_MAX_TOKENS_QUERY,
    MIN_TICKETS_FOR_GROUP, SYSTEM_MESSAGE, MAX_LOOKBACK_HOURS, DEFAULT_QUERY_HOURS, LARGE_RESULT_THRESHOLD
)

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ticket_analyzer')

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def prepare_ticket_texts(tickets):
    """Convert tickets to formatted text for OpenAI analysis"""
    return [
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
        f"Link to Discourse: {t.get('link_to_discourse', '')}, "
        f"Assignee: {t.get('assignee', '')}"
        for t in tickets
    ]

def call_openai_api(messages, max_tokens, analysis_type="analysis"):
    """Unified OpenAI API caller with error handling"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OpenAI API key not found")
        return None, False
    
    try:
        logger.info(f"Calling OpenAI API for {analysis_type}")
        
        # Add system message to enforce compact JSON formatting
        enhanced_messages = []
        for msg in messages:
            if msg["role"] == "system":
                enhanced_content = msg["content"] + " Always return compact JSON without formatting or newlines."
                enhanced_messages.append({"role": "system", "content": enhanced_content})
            else:
                enhanced_messages.append(msg)
        
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=enhanced_messages,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=max_tokens
        )
        result = response.choices[0].message.content.strip()
        logger.info(f"Received response from OpenAI for {analysis_type}")
        return result, True
    except Exception as e:
        logger.error(f"Error calling OpenAI API for {analysis_type}: {e}")
        return None, False

def parse_openai_response(response_text, expected_type="unknown"):
    """Parse OpenAI response with robust JSON handling"""
    try:
        cleaned = response_text.strip()
        
        # Remove markdown code blocks if present
        if cleaned.startswith("```"):
            cleaned = cleaned.strip('`').strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].lstrip('\n').lstrip()
        
        # Remove JavaScript-style comments and trailing commas
        cleaned = re.sub(r'//.*?(?=\n|$)', '', cleaned)
        cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
        
        # For pretty-formatted JSON, try to parse directly first
        # If that fails, we'll do more aggressive cleaning below
        try:
            parsed = json.loads(cleaned)
            logger.info(f"Successfully parsed {expected_type} response on first attempt")
            return parsed, True
        except json.JSONDecodeError:
            logger.info(f"Initial parse failed, attempting aggressive cleaning for {expected_type}")
        
        # More aggressive cleaning for problematic responses
        # Remove all unnecessary whitespace and newlines
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Replace all whitespace with single spaces
        cleaned = cleaned.strip()
        
        # Fix common JSON formatting issues
        cleaned = re.sub(r',\s*}', '}', cleaned)  # Remove trailing commas before }
        cleaned = re.sub(r',\s*]', ']', cleaned)  # Remove trailing commas before ]
        
        logger.info(f"Attempting to parse cleaned compact JSON for {expected_type}")
        parsed = json.loads(cleaned)
        logger.info(f"Successfully parsed {expected_type} response after cleaning")
        return parsed, True
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {e}")
        logger.error(f"JSON error at line {getattr(e, 'lineno', 'unknown')}, column {getattr(e, 'colno', 'unknown')}, position {getattr(e, 'pos', 'unknown')}")
        
        # Log problematic area for debugging
        if hasattr(e, 'pos') and e.pos is not None and e.pos < len(response_text):
            start = max(0, e.pos - 30)
            end = min(len(response_text), e.pos + 30)
            problem_area = response_text[start:end]
            logger.error(f"Problem area: {repr(problem_area)}")
        
        logger.error(f"Raw response (first 300 chars): {response_text[:300]}...")
        return None, False
        
    except Exception as e:
        logger.error(f"Unexpected error parsing OpenAI response: {e}")
        logger.error(f"Raw response: {response_text[:200]}...")
        return None, False

def analyze_similar_tickets(tickets):
    """Analyze tickets to find groups of similar issues using OpenAI"""
    if not tickets:
        logger.info("No tickets provided for analysis")
        return []
    
    logger.info(f"Analyzing {len(tickets)} tickets for similarity")
    return cluster_with_openai(tickets)

def cluster_with_openai(tickets):
    """Group tickets by similarity using OpenAI's completion API"""
    ticket_texts = prepare_ticket_texts(tickets)
    logger.info(f"Prepared {len(ticket_texts)} ticket texts for OpenAI analysis")
    
    prompt = f"""
    I have a set of Amplitude customer support tickets from various product analytics implementations.
    
    As an Amplitude product analytics expert with access to current Amplitude documentation (docs.amplitude.com) and knowledge base, analyze these tickets and identify groups that represent the same underlying technical or product analytics issues.
    
    Leverage your knowledge of Amplitude's current product suite, common implementation patterns, and known customer pain points as documented in Amplitude's help center and documentation. Group tickets by their underlying root cause, not just surface-level symptoms.
    
    Consider the full spectrum of Amplitude products and integrations, including but not limited to issues related to:
    - Product implementation and configuration challenges
    - Data collection and integration problems
    - Analytics and reporting difficulties  
    - Platform performance and infrastructure issues
    - Account management and access problems
    
    Use your expertise to identify patterns that indicate systemic product issues versus individual customer configuration problems.
    
    Return your response as a JSON object with this exact structure:
    {OPENAI_CLUSTERING_FORMAT.format(total_tickets=len(tickets))}
    
    CRITICAL FORMATTING REQUIREMENTS:
    - Return ONLY compact JSON with NO pretty-printing, NO newlines, NO extra spaces
    - Only create groups with {MIN_TICKETS_FOR_GROUP}+ tickets that genuinely represent the same underlying issue
    - ticket_ids must be strings containing ONLY the numeric ID without any prefix or suffix
    - IMPORTANT: Only include ticket IDs in "ticket_ids" array
    - Update groups_found to the actual number of groups returned
    - Set "large_result_set" to true ONLY if creating groups with total tickets > {LARGE_RESULT_THRESHOLD}
    - NO comments, explanations, markdown formatting, or additional text
    - JSON must be valid and parseable in a single line
    
    Here are the tickets:
    {ticket_texts}
    """
    
    messages = [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": prompt}
    ]
    
    result, success = call_openai_api(messages, OPENAI_MAX_TOKENS_CLUSTERING, "ticket clustering")
    if not success:
        return []
    
    parsed_data, success = parse_openai_response(result, "clustering")
    if not success:
        return []
    
    # Return groups in unified format with only ticket_ids
    groups = parsed_data.get("data", {}).get("groups", [])
    similar_groups = []
    
    for group in groups:
        ticket_ids = group.get('ticket_ids', [])
        logger.info(f"Processing group '{group.get('issue_type')}' with {len(ticket_ids)} tickets")
        
        # Validate ticket IDs exist in our dataset
        valid_ticket_ids = [tid for tid in ticket_ids if any(str(t['id']) == str(tid) for t in tickets)]
        
        if len(valid_ticket_ids) >= MIN_TICKETS_FOR_GROUP:
            ticket_group = {
                'issue_type': group.get('issue_type'),
                'ticket_ids': valid_ticket_ids,  # Use unified format with only IDs
                'count': len(valid_ticket_ids)
            }
            similar_groups.append(ticket_group)
            logger.info(f"Added group '{group.get('issue_type')}' with {len(valid_ticket_ids)} tickets")
        else:
            logger.info(f"Skipping group '{group.get('issue_type')}' as it has fewer than {MIN_TICKETS_FOR_GROUP} tickets")
    
    return similar_groups

def analyze_tickets_with_query_and_timeframe(tickets, query, custom_timeframe=None):
    """Analyze tickets with a custom query using OpenAI, with support for dynamic time windows"""
    if not query:
        logger.info("No query provided for analysis")
        return None, "No query provided.", None
    
    # Extract time window and get cleaned query from OpenAI
    time_window_info = custom_timeframe or extract_time_window_and_clean_query(query)
    logger.info(f"Using time window: {time_window_info}")
    
    # Extract cleaned query from time window info
    cleaned_query = time_window_info.get("cleaned_query", query)
    
    # Fetch tickets based on time window
    tickets = get_tickets_for_timeframe(tickets, time_window_info, custom_timeframe)
    if not tickets:
        logger.info("No tickets found for analysis with query")
        return None, "No tickets found for the specified time window.", time_window_info
    
    logger.info(f"Analyzing {len(tickets)} tickets with custom query: {cleaned_query}")
    
    # Prepare data and make API call
    ticket_texts = prepare_ticket_texts(tickets)
    time_context = f"These tickets were collected from the {time_window_info.get('description', 'last 24 hours')}."
    
    prompt = f"""
    You are analyzing Amplitude customer support tickets as a senior product analytics expert. Here is a list of support tickets from Amplitude customers across various industries and product types:
    {ticket_texts}

    {time_context}

    Please answer the following question based on the tickets above, leveraging your deep knowledge of Amplitude's product analytics platform:
    {cleaned_query}

    ANALYSIS INSTRUCTIONS:
    - Apply your comprehensive knowledge of Amplitude's current product suite (as documented in docs.amplitude.com) to group findings into meaningful categories
    - Reference your understanding of Amplitude's product documentation and help center to identify which product areas and features are affected
    - Use your expertise in Amplitude's ecosystem to identify patterns that indicate systemic issues vs. individual configuration problems
    - Each group should contain tickets that relate to the same underlying product analytics issue or workflow based on current Amplitude product architecture
    - Consider customer implementation patterns and common challenges as documented in Amplitude's knowledge base
    - CRITICAL: Set "large_result_set" to true ONLY if total relevant tickets > {LARGE_RESULT_THRESHOLD} (more than {LARGE_RESULT_THRESHOLD})
    - CRITICAL: Set "large_result_set" to false if total relevant tickets ≤ {LARGE_RESULT_THRESHOLD} (equal to or less than {LARGE_RESULT_THRESHOLD})
    - Only provide ticket IDs in the "ticket_ids" array for each group
    - Always update "count" for each group to reflect the actual number of tickets in that group
    - Update "total_tickets" to reflect the sum of all relevant tickets across all groups
    - In your summary, always use ACTUAL COUNTS of tickets found, not threshold numbers
    - Make summary concise but informative, mentioning the number of groups and total tickets with relevant product context
    - Consider the time window context in your analysis and any potential correlation with recent product updates or feature releases

    Return your response as a JSON object with this exact structure:
    {OPENAI_QUERY_FORMAT.format(total_tickets=len(tickets), query=query)}
    
    CRITICAL FORMATTING REQUIREMENTS:
    - Return ONLY compact JSON with NO pretty-printing, NO newlines, NO extra spaces
    - NO comments, explanations, markdown formatting, or additional text
    - JSON must be valid and parseable in a single line
    - Do not include any text before or after the JSON object
    """
    
    messages = [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": prompt}
    ]
    
    result, success = call_openai_api(messages, OPENAI_MAX_TOKENS_QUERY, "custom query analysis")
    if not success:
        return None, "OpenAI API key not configured.", time_window_info
    
    parsed_data, success = parse_openai_response(result, "query")
    if not success:
        return None, result, time_window_info
    
    # Enrich with organization data and add time window to metadata
    parsed_data = enrich_response_with_org_data(parsed_data, tickets)
    if parsed_data and "metadata" in parsed_data:
        parsed_data["metadata"]["time_window"] = time_window_info
    
    summary = parsed_data.get("summary", "No summary available")
    time_desc = time_window_info.get("description", "last 24 hours")
    enhanced_summary = f"{summary} (Data from {time_desc})"
    
    logger.info(f"Parsed query response successfully. Enhanced summary: {enhanced_summary}")
    return parsed_data, enhanced_summary, time_window_info



def get_tickets_for_timeframe(tickets, time_window_info, custom_timeframe):
    """Get appropriate tickets based on time window information"""
    from zendesk_client import fetch_recent_tickets_by_hours
    
    if time_window_info.get("has_time_reference", False) or custom_timeframe is not None:
        hours = time_window_info.get("hours", DEFAULT_QUERY_HOURS)
        logger.info(f"Fetching tickets from last {hours} hours based on query time reference")
        return fetch_recent_tickets_by_hours(hours)
    else:
        if not tickets:
            logger.info("No tickets provided and no time reference found, fetching default tickets")
            return fetch_recent_tickets_by_hours(DEFAULT_QUERY_HOURS)
        return tickets

def extract_time_window_and_clean_query(query):
    """Extract time window information and clean query using OpenAI"""
    if not query:
        logger.warning("No query provided for time window extraction")
        return create_default_time_window("No query provided", query)
    
    logger.info(f"Extracting time window and cleaning query: {query}")
    
    prompt = f"""
    Analyze the following user query and perform two tasks:
    
    1. Extract any time references (like "last week", "yesterday", "past 3 days", "previous month", etc.)
    2. Remove time references from the query while preserving the core question
    
    Query: "{query}"
    
    For time extraction:
    - If there is a time reference, convert it to hours and provide a human-readable description
    - If there is no time reference, set has_time_reference to false and use the default
    - Maximum lookback allowed: {MAX_LOOKBACK_HOURS} hours ({MAX_LOOKBACK_HOURS // 24} days)
    - Default time window: {DEFAULT_QUERY_HOURS} hours
    
    For query cleaning:
    - Remove phrases like "last week", "in the past month", "yesterday", etc.
    - Keep the core question about ticket content, issues, or analysis
    - Ensure the cleaned query is grammatically correct and meaningful
    - If removing time references would make the query empty or unclear, keep essential context
    
    Common time conversions:
    - "last hour" = 1 hour
    - "last 24 hours" / "yesterday" = 24 hours  
    - "last 2 days" = 48 hours
    - "last week" = 168 hours (7 days)
    - "last month" = 720 hours (30 days)
    - "last 2 months" = 1440 hours (60 days)
    
    Return your response as a JSON object with this exact structure:
    {OPENAI_TIME_WINDOW_FORMAT}
    
    CRITICAL FORMATTING REQUIREMENTS:
    - Return ONLY compact JSON with NO pretty-printing, NO newlines, NO extra spaces
    - If the requested time window exceeds the maximum lookback ({MAX_LOOKBACK_HOURS} hours), cap it at the maximum
    - Be conservative with ambiguous time references
    - Ensure cleaned_query is meaningful and actionable for ticket analysis
    - NO comments, explanations, markdown formatting, or additional text
    - JSON must be valid and parseable in a single line
    """
    
    messages = [
        {"role": "system", "content": "You are an expert Amplitude product analytics professional with comprehensive knowledge of Amplitude's documentation and customer support patterns. You understand time-sensitive analytics queries and how they relate to current Amplitude product workflows."},
        {"role": "user", "content": prompt}
    ]
    
    result, success = call_openai_api(messages, 1000, "time window and query cleaning")
    if not success:
        return create_default_time_window("OpenAI API key not available", query)
    
    try:
        parsed_result = json.loads(result)
        logger.info(f"Successfully parsed time window and cleaned query: {parsed_result}")
        
        # Extract and validate time window information
        has_time_reference = parsed_result.get("has_time_reference", False)
        hours = parsed_result.get("time_window", {}).get("hours", DEFAULT_QUERY_HOURS)
        description = parsed_result.get("time_window", {}).get("description", f"last {hours} hours")
        cleaned_query = parsed_result.get("cleaned_query", query)
        reasoning = parsed_result.get("reasoning", "Extracted from query")
        
        # Ensure hours is within bounds
        if hours > MAX_LOOKBACK_HOURS:
            logger.warning(f"Time window {hours} hours exceeds maximum {MAX_LOOKBACK_HOURS} hours, capping it")
            hours = MAX_LOOKBACK_HOURS
            description = f"last {MAX_LOOKBACK_HOURS // 24} days (capped at maximum)"
            reasoning += f" (capped at maximum lookback of {MAX_LOOKBACK_HOURS} hours)"
        
        # Validate cleaned query
        if not cleaned_query or cleaned_query.strip() == "":
            logger.warning("OpenAI returned empty cleaned query, using original")
            cleaned_query = query
        
        if cleaned_query != query:
            logger.info(f"OpenAI cleaned query: '{query}' → '{cleaned_query}'")
        
        return {
            "has_time_reference": has_time_reference,
            "hours": hours,
            "description": description,
            "cleaned_query": cleaned_query,
            "reasoning": reasoning
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse time window JSON response: {e}")
        logger.error(f"Raw response: {result}")
        return create_default_time_window(f"Failed to parse OpenAI response: {e}", query)

def create_default_time_window(reason, query=""):
    """Create default time window configuration"""
    return {
        "has_time_reference": False,
        "hours": DEFAULT_QUERY_HOURS,
        "description": f"last {DEFAULT_QUERY_HOURS} hours",
        "cleaned_query": query,
        "reasoning": reason
    }

def enrich_response_with_org_data(parsed_data, original_tickets):
    """Enrich OpenAI response with ticket data from original Zendesk tickets"""
    if not parsed_data or not original_tickets:
        return parsed_data
    
    ticket_lookup = {str(ticket['id']): ticket for ticket in original_tickets}
    data = parsed_data.get('data', {})
    
    # Handle groups format (new unified format)
    if 'groups' in data and data['groups']:
        enriched_groups = []
        all_ticket_ids = []
        
        for group in data['groups']:
            enriched_group = group.copy()
            
            # Enrich detailed ticket objects for smaller result sets
            if 'tickets' in group and group['tickets']:
                enriched_group['tickets'] = enrich_ticket_list(group['tickets'], ticket_lookup)
            
            # Collect ticket IDs for org summary
            if 'ticket_ids' in group:
                all_ticket_ids.extend(group['ticket_ids'])
            
            enriched_groups.append(enriched_group)
        
        data['groups'] = enriched_groups
        
        # Create org summary for large result sets
        if parsed_data.get('large_result_set', False) and all_ticket_ids:
            add_org_summary_to_metadata(parsed_data, all_ticket_ids, ticket_lookup)
    
    # Handle legacy tickets format for backwards compatibility
    elif 'tickets' in data and data['tickets']:
        data['tickets'] = enrich_ticket_list(data['tickets'], ticket_lookup)
        
        # Create org summary for large result sets
        if parsed_data.get('large_result_set', False) and 'ticket_ids' in data:
            add_org_summary_to_metadata(parsed_data, data['ticket_ids'], ticket_lookup)
    
    return parsed_data

def enrich_ticket_list(tickets, ticket_lookup):
    """Enrich a list of tickets with original Zendesk data"""
    enriched_tickets = []
    
    for ticket in tickets:
        ticket_id = str(ticket.get('ticket_id', ''))
        if ticket_id in ticket_lookup:
            original_ticket = ticket_lookup[ticket_id]
            enriched_ticket = ticket.copy()
            
            # Add organization and assignee info
            enriched_ticket['org_id'] = original_ticket.get('numeric_org_id', '')
            if original_ticket.get('assignee'):
                enriched_ticket['assignee'] = original_ticket['assignee']
            
            # Add JIRA and Discourse links
            for field in ['jira_id', 'jira_ticket_id', 'link_to_discourse']:
                if original_ticket.get(field):
                    enriched_ticket[field] = original_ticket[field]
            
            enriched_tickets.append(enriched_ticket)
            logger.debug(f"Enhanced ticket #{ticket_id} with org_id: {original_ticket.get('numeric_org_id', 'N/A')}")
        else:
            enriched_tickets.append(ticket)
            logger.warning(f"Could not find original data for ticket #{ticket_id}")
    
    return enriched_tickets

def add_org_summary_to_metadata(parsed_data, ticket_ids, ticket_lookup):
    """Add organization summary to metadata for large result sets"""
    org_summary = {}
    
    for ticket_id in ticket_ids:
        if str(ticket_id) in ticket_lookup:
            original_ticket = ticket_lookup[str(ticket_id)]
            org_id = original_ticket.get('numeric_org_id')
            if org_id:
                org_key = f"Organization {org_id}"
                if org_key not in org_summary:
                    org_summary[org_key] = {'org_id': org_id, 'count': 0}
                org_summary[org_key]['count'] += 1
    
    if org_summary:
        if 'metadata' not in parsed_data:
            parsed_data['metadata'] = {}
        parsed_data['metadata']['organizations'] = org_summary
        logger.info(f"Added organization summary for large result set: {len(org_summary)} orgs")

 