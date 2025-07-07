# Zendesk Alert System

A streamlined system that monitors Zendesk tickets for similar issues and sends Slack alerts when patterns are detected. Features AI-powered analysis, custom query capabilities, and flexible monitoring options.

## Quick Setup

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**

   ```bash
   # Zendesk API credentials
   export ZENDESK_URL="https://yourcompany.zendesk.com"
   export ZENDESK_EMAIL="your-email@company.com"
   export ZENDESK_TOKEN="your_api_token_here"

   # OpenAI API key (required for analysis)
   export OPENAI_API_KEY="your_openai_key_here"

   # Slack webhook URL (optional for testing)
   export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

   # Alert threshold (default: 5)
   export TICKET_CNT_THRESHOLD="5"
   ```

## Usage

### Main Application

**Run Once (Single Check):**

```bash
python app.py                    # Default: single check
python app.py --once            # Explicit single check
```

**Continuous Monitoring:**

```bash
python app.py --monitor         # Hourly checks with scheduler
```

**Custom Query Analysis:**
Analyze tickets with custom questions and get AI-powered insights:

```bash
# Ask specific questions about your tickets
python app.py --query "How many login related tickets do we have?"
python app.py --query "What are the most common SDK issues?"
python app.py --query "Which tickets mention billing problems?"
python app.py --query "Summarize all high priority tickets"
python app.py --query "What billing issues happened this week?"
```

**Help:**

```bash
python app.py --help           # Show all available commands
```

### Testing & Debugging

```bash
# Run all tests
python test.py

# Test specific components
python test.py env          # Environment variables
python test.py zendesk      # Zendesk API connection
python test.py analysis     # Ticket analysis with sample data
python test.py slack        # Slack notifications
python test.py fields       # List all available Zendesk fields

# Test with Slack notifications enabled
SEND_TEST_SLACK=true python test.py slack
```

## Features

### 🤖 AI-Powered Analysis

- **Automatic Clustering**: Groups similar tickets using OpenAI GPT-4
- **Custom Queries**: Ask questions about your ticket data in natural language
- **Smart Field Extraction**: Analyzes custom Zendesk fields for better context

### 📊 Rich Data Analysis

- **Custom Field Support**: Extracts and analyzes Zendesk custom fields including:
  - Internal Chart/Tool information
  - Steps to reproduce
  - Request types and classifications
  - JIRA ticket references
  - SDK platform details
- **Unified JSON Format**: Consistent response structure for all analysis types

### 🔔 Smart Notifications

- **Slack Integration**: Rich formatted alerts with ticket links
- **Flexible Thresholds**: Configurable alert triggers
- **Custom Summaries**: AI-generated summaries for query results

## How It Works

**Pattern Detection Mode** (`python app.py --once` or `--monitor`):

1. **Fetches** recent tickets from Zendesk API (last 24 hours)
2. **Extracts** custom fields and metadata for enhanced analysis
3. **Analyzes** tickets using OpenAI to identify similar issue patterns
4. **Alerts** via Slack when groups of 5+ similar tickets are detected
5. **Fallback** to sample data if Zendesk API is unavailable

**Custom Query Mode** (`python app.py --query "..."`):

1. **Extracts** time window from your query (if specified)
2. **Fetches** relevant tickets based on time window or defaults to 24 hours
3. **Analyzes** tickets using OpenAI to answer your specific question
4. **Sends** formatted results and insights to Slack
5. **Supports** natural language queries about trends, issues, and patterns

## Files

- `app.py` - **Main application** with scheduler, pattern detection, and custom query analysis
- `test.py` - **Testing tool** for debugging and validating system components
- `zendesk_client.py` - Zendesk API integration with custom field extraction
- `ticket_analyzer.py` - OpenAI-powered analysis with unified JSON format
- `slack_notifier.py` - Enhanced Slack webhook notifications
- `constants.py` - Centralized configuration and format templates
- `sample_tickets.json` - Sample data for testing

## Environment Variables

| Variable               | Required | Default | Description                           |
| ---------------------- | -------- | ------- | ------------------------------------- |
| `ZENDESK_URL`          | Yes      | -       | Your Zendesk instance URL             |
| `ZENDESK_EMAIL`        | Yes      | -       | Your Zendesk email                    |
| `ZENDESK_TOKEN`        | Yes      | -       | Your Zendesk API token                |
| `OPENAI_API_KEY`       | Yes      | -       | OpenAI API key for AI analysis        |
| `SLACK_WEBHOOK_URL`    | No       | -       | Slack webhook for notifications       |
| `TICKET_CNT_THRESHOLD` | No       | 5       | Minimum tickets to trigger alert      |
| `SEND_TEST_SLACK`      | No       | false   | Send test notifications in debug mode |

## Custom Fields Analyzed

The system automatically extracts and analyzes these Zendesk custom fields:

- **Internal Chart/Tool** - AI tagged and generated information
- **Steps to reproduce** - Detailed reproduction steps
- **Request Type** - AI tagged and CNIL classifications
- **Requester Type** - Customer classification
- **JIRA Integration** - JIRA IDs and ticket references
- **Documentation Links** - Discourse and other reference links

## Examples

### Automatic Pattern Detection

```bash
# System automatically detects when 5+ tickets have similar issues
python app.py --once
# → Sends Slack alert: "🚨 Alert: 7 Similar Support Tickets Detected"
```

### Continuous Monitoring

```bash
# Monitor for patterns every hour
python app.py --monitor
# → Runs continuously, checking every hour for new patterns
```

### Custom Analysis

```bash
# Get insights about specific issues
python app.py --query "How many tickets are related to SDK integration?"
# → Returns: "Found 12 SDK-related tickets across iOS, Android, and Web platforms"

python app.py --query "What are the top 3 most common issues this week?"
# → Returns: Ranked list of issues with ticket counts and examples

python app.py --query "Which organizations reported the most billing issues?"
# → Returns: Analysis of billing issues by organization with counts
```
