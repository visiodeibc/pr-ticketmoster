# OpenAI Response Format Templates
OPENAI_CLUSTERING_FORMAT = '''{{
  "response_type": "clustering",
  "summary": "Brief summary suitable for Slack",
  "large_result_set": false,
  "data": {{
    "groups": [
      {{
        "issue_type": "Descriptive name for the issue or answer category",
        "ticket_ids": ["123", "456", "789"],
        "count": 3
      }}
    ],
    "total_tickets": 0
  }},
  "metadata": {{
    "total_tickets_analyzed": {total_tickets},
    "groups_found": 0
  }}
}}'''

OPENAI_QUERY_FORMAT = '''{{
  "response_type": "query",
  "summary": "Brief summary suitable for Slack",
  "large_result_set": false,
  "data": {{
    "groups": [
      {{
        "issue_type": "Descriptive name for the issue or answer category",
        "ticket_ids": ["123", "456", "789"],
        "count": 3
      }}
    ],
    "total_tickets": 0
  }},
  "metadata": {{
    "total_tickets_analyzed": {total_tickets},
    "query": "{query}"
  }}
}}'''

OPENAI_TIME_WINDOW_FORMAT = '''{{
  "response_type": "time_window",
  "has_time_reference": true,
  "time_window": {{
    "hours": 24,
    "description": "last 24 hours"
  }},
  "cleaned_query": "Query with time references removed for content analysis",
  "reasoning": "Brief explanation of why this time window was extracted"
}}'''

# OpenAI Configuration
OPENAI_MODEL = "gpt-4.1-2025-04-14"
OPENAI_TEMPERATURE = 0.2
OPENAI_MAX_TOKENS_CLUSTERING = 20000
OPENAI_MAX_TOKENS_QUERY = 20000
SYSTEM_MESSAGE = "You are a senior Amplitude product analytics professional with comprehensive knowledge of Amplitude's full product suite and ecosystem. You stay current with Amplitude's product documentation (docs.amplitude.com), help center, and knowledge base to understand all current products, features, integrations, and common customer implementation patterns. You can identify support ticket patterns across all Amplitude products and integrations, understanding both technical implementation challenges and business use case requirements across different industries and product types."

# Slack Configuration
SLACK_MAX_TEXT_LENGTH = 3000
SLACK_MAX_BLOCKS = 50

# Zendesk Custom Field Mapping (Field ID -> Key Name)
CUSTOM_FIELD_MAP = {
    31731966344603: 'internal_chart_tool_ai_tagged',
    31733696813723: 'internal_chart_tool_ai_generated',
    13905556187419: 'steps_to_reproduce',
    34956827393051: 'request_type_ai_tagged',
    16461228458907: 'request_type_cnil',
    14495072558491: 'requester_type',
    16232951560219: 'jira_id',
    360002325512: 'jira_ticket_id',
    9870708900891: 'link_to_discourse',
    114101027932: 'internal_chart_tool',
    9870197721883: 'numeric_org_id',
    24388397: 'assignee',
}

# Analysis Configuration
MIN_TICKETS_FOR_GROUP = 5
TICKET_FETCH_HOURS = 24
LARGE_RESULT_THRESHOLD = 20

# Time Window Configuration
MAX_LOOKBACK_HOURS = 24 * 60  # 2 months (60 days)
DEFAULT_QUERY_HOURS = 24

# Environment Variables
REQUIRED_ENV_VARS = ['ZENDESK_URL', 'ZENDESK_EMAIL', 'ZENDESK_TOKEN', 'OPENAI_API_KEY']
OPTIONAL_ENV_VARS = ['SLACK_WEBHOOK_URL', 'TICKET_CNT_THRESHOLD', 'SEND_TEST_SLACK']

# External Services
JIRA_BASE_URL = "https://amplitude.atlassian.net/browse"
DEFAULT_SEND_TEST_SLACK = False