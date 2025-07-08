# Zendesk Alert System

A streamlined AI-powered system that monitors Zendesk tickets for similar issues and sends intelligent Slack alerts. Features automatic pattern detection, custom query analysis, and comprehensive Amplitude product analytics expertise.

## What You Can Do With This Project

### 🔍 **Automatic Issue Detection**

• **Detect recurring problems** - Automatically find when 5+ tickets report the same issue

- _Example: System detects 12 tickets about "chart loading failures" and alerts your team_

### 🤖 **Ask Questions About Your Tickets**

• **Get instant insights** - Ask natural language questions about your support data

- _Example: "How many billing issues happened this week?" → "Found 8 billing tickets: 3 payment failures, 5 plan upgrades"_

### 📊 **Product Analytics Intelligence**

• **Amplitude expertise** - Specialized knowledge of product analytics, experimentation, and data integration issues

- _Example: Identifies "Experiment assignment issues" vs generic "API errors"_

### ⚡ **Real-time Monitoring**

• **Continuous oversight** - Monitor ticket patterns hourly or run on-demand checks

- _Example: Detects surge in SDK integration problems during a product release_

### 🔔 **Smart Slack Notifications**

• **Rich alerts** - Get detailed notifications with clickable ticket links and context

- _Example: "🚨 Alert: 7 Similar Support Tickets Detected - Chart Loading Failures in Analytics Dashboards"_

---

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

   # Slack webhook URL (optional for notifications)
   export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

   # Alert threshold (default: 5)
   export TICKET_CNT_THRESHOLD="5"
   ```

## Usage

### 🔍 **Pattern Detection (Automatic Issue Discovery)**

**Run Once (Single Check):**

```bash
python app.py                    # Default: single check
python app.py --once            # Explicit single check
```

_→ Analyzes last 24 hours of tickets, groups similar issues, sends Slack alert if 5+ tickets match_

**Continuous Monitoring:**

```bash
python app.py --monitor         # Hourly checks with scheduler
```

_→ Runs continuously, checking every hour for emerging patterns_

### 🤖 **Custom Query Analysis (Ask Anything)**

Ask natural language questions about your tickets:

```bash
# Volume and trends
python app.py --query "How many experiment related tickets did we get today?"
python app.py --query "What are the most common SDK issues this week?"

# Specific problems
python app.py --query "Which tickets mention billing problems?"
python app.py --query "How many chart loading failures happened?"

# Customer insights
python app.py --query "Which organizations reported the most API issues?"
python app.py --query "What integration problems are customers facing?"

# Time-based analysis
python app.py --query "What billing issues happened this week?"
python app.py --query "Show me dashboard problems from yesterday"
```

### 🛠 **Testing & Debugging**

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

## Key Features

### 🤖 **AI-Powered Analysis with Amplitude Expertise**

• **Specialized Knowledge** - Trained on Amplitude's product documentation and common customer pain points

- _Example: Distinguishes "funnel configuration issues" from general "chart problems"_

• **Automatic Clustering** - Groups similar tickets using OpenAI GPT-4 with product analytics context

- _Example: Groups "user identification", "session tracking", and "anonymous users" into "User Management Issues"_

• **Custom Queries** - Ask questions in natural language and get intelligent answers

- _Example: "SDK integration problems" → Lists iOS, Android, Web SDK issues with root cause analysis_

### 📊 **Rich Data Analysis**

• **Custom Field Extraction** - Analyzes Zendesk custom fields for enhanced context:

- Internal Chart/Tool information
- Steps to reproduce
- Request types and classifications
- JIRA ticket references
- Assignee and organization data
- _Example: Links JIRA tickets to support tickets for engineering context_

• **Unified JSON Format** - Consistent, reliable response structure for all analysis types

- _Example: Same format whether asking about "billing issues" or detecting "API problems"_

• **Time Window Intelligence** - Automatically extracts time references from queries

- _Example: "last week's experiment issues" → Analyzes last 7 days of experiment-related tickets_

### 🔔 **Smart Slack Notifications**

• **Rich Formatting** - Professional alerts with clickable ticket links and context

- _Example: Shows ticket #123456 with JIRA link, assignee, and organization info_

• **Intelligent Grouping** - Different formats for different result sizes

- _Example: 3 tickets → Full details with links; 25 tickets → Compact summary with counts_

• **Contextual Summaries** - AI-generated summaries tailored to the query or pattern

- _Example: "Found 12 experiment assignment issues affecting 4 organizations, primarily related to feature flag configuration"_

## How It Works

### 🔍 **Pattern Detection Mode** (`--once` or `--monitor`)

1. **Fetches** recent tickets from Zendesk API (last 24 hours)
2. **Extracts** custom fields and metadata for enhanced analysis
3. **Analyzes** tickets using OpenAI with Amplitude product expertise
4. **Groups** similar issues using AI clustering (minimum 5 tickets per group)
5. **Alerts** via Slack when patterns are detected with rich formatting
6. **Fallback** to sample data if Zendesk API is unavailable

_Example Flow: 86 tickets → AI finds 17 "chart loading failures" → Slack alert with ticket links_

### 🤖 **Custom Query Mode** (`--query`)

1. **Extracts** time window from your question (if specified)
2. **Fetches** relevant tickets based on time window or defaults to 24 hours
3. **Analyzes** tickets using OpenAI with Amplitude product knowledge
4. **Answers** your specific question with categorized results
5. **Sends** formatted insights to Slack with supporting data
6. **Supports** complex queries about trends, issues, and customer patterns

_Example Flow: "billing issues this week" → Analyzes 7 days → Finds 8 tickets → Groups by problem type → Slack summary_

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

• **Internal Chart/Tool** - AI tagged and generated information
• **Steps to reproduce** - Detailed reproduction steps  
• **Request Type** - AI tagged and CNIL classifications
• **Requester Type** - Customer classification
• **JIRA Integration** - JIRA IDs and ticket references
• **Documentation Links** - Discourse and other reference links
• **Organization Data** - Customer organization and assignee information

## Real-World Examples

### 🔍 **Automatic Pattern Detection**

```bash
python app.py --once
```

**Result:** _"🚨 Alert: 12 Similar Support Tickets Detected - Experiment Assignment Issues in Feature Flag Configuration"_

- Lists all affected tickets with links
- Shows organizations impacted
- Includes JIRA tickets for engineering follow-up

### 🤖 **Custom Analysis Queries**

```bash
python app.py --query "What SDK integration issues happened this week?"
```

**Result:** _"Found 15 SDK integration tickets across 3 platforms: iOS (6 tickets), Android (5 tickets), Web (4 tickets). Main issues: authentication failures, event tracking problems, session management."_

```bash
python app.py --query "How many experiment related tickets did we get today?"
```

**Result:** _"Identified 8 experiment-related tickets in 3 categories: Assignment Issues (3), Analysis Problems (3), Feature Flag Configuration (2)."_

```bash
python app.py --query "Which organizations reported the most billing issues?"
```

**Result:** _"Top 3 organizations by billing issues: Company A (4 tickets), Company B (3 tickets), Company C (2 tickets). Issues: payment failures, plan upgrades, quota exceeded."_

## Project Files

- `app.py` - **Main application** with scheduler, pattern detection, and custom query analysis
- `test.py` - **Testing tool** for debugging and validating system components
- `zendesk_client.py` - Zendesk API integration with custom field extraction
- `ticket_analyzer.py` - OpenAI-powered analysis with Amplitude expertise
- `slack_notifier.py` - Enhanced Slack webhook notifications with sanitization
- `constants.py` - Centralized configuration and format templates
- `sample_tickets.json` - Sample data for testing
