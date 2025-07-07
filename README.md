# Zendesk Alert System

A streamlined system that monitors Zendesk tickets for similar issues and sends Slack alerts when patterns are detected. Features AI-powered analysis and custom query capabilities.

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

### Run Once (Single Check)

```bash
python app.py --once
```

### Run Continuous Monitoring (Hourly Checks)

```bash
python app.py
```

### Custom Query Analysis

Analyze tickets with custom questions and get AI-powered insights:

```bash
# Ask specific questions about your tickets
python checker.py query "How many login related tickets do we have?"
python checker.py query "What are the most common SDK issues?"
python checker.py query "Which tickets mention billing problems?"
python checker.py query "Summarize all high priority tickets"
```

### Test the System

```bash
# Run all tests
python checker.py

# Test specific components
python checker.py env          # Environment variables
python checker.py zendesk      # Zendesk API connection
python checker.py analysis     # Ticket analysis with sample data
python checker.py slack        # Slack notifications
python checker.py fields       # List all available Zendesk fields

# Test with Slack notifications enabled
SEND_TEST_SLACK=true python checker.py slack
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

1. **Fetches** recent tickets from Zendesk API (last 24 hours)
2. **Extracts** custom fields and metadata for enhanced analysis
3. **Analyzes** tickets using OpenAI to identify patterns or answer queries
4. **Alerts** via Slack when patterns are detected or query results are ready
5. **Fallback** to sample data if Zendesk API is unavailable

## Files

- `app.py` - Main application with scheduler
- `checker.py` - Unified testing and query tool
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

### Custom Analysis

```bash
# Get insights about specific issues
python checker.py query "How many tickets are related to SDK integration?"
# → Returns: "Found 12 SDK-related tickets across iOS, Android, and Web platforms"

python checker.py query "What are the top 3 most common issues this week?"
# → Returns: Ranked list of issues with ticket counts and examples
```
