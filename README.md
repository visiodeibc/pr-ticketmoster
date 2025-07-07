# Zendesk Alert System

A streamlined system that monitors Zendesk tickets for similar issues and sends Slack alerts when patterns are detected.

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

   # Slack webhook URL (optional for testing)
   export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

   # Alert threshold (default: 5)
   export TICKET_CNT_THRESHOLD="5"

   # OpenAI API key
   export OPENAI_API_KEY="your_openai_key_here"
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

### Test the System

```bash
# Run all tests
python debug_checker.py

# Test specific components
python debug_checker.py env          # Environment variables
python debug_checker.py zendesk      # Zendesk API connection
python debug_checker.py analysis     # Ticket analysis
python debug_checker.py slack        # Slack notifications

# Test with Slack notifications enabled
SEND_TEST_SLACK=true python debug_checker.py slack
```

## How It Works

1. **Fetches** recent tickets from Zendesk API (last 24 hours)
2. **Analyzes** tickets using OpenAI to identify similar issues
3. **Alerts** via Slack when 5+ tickets have the same issue type
4. **Fallback** to sample data if Zendesk API is unavailable

## Files

- `app.py` - Main application with scheduler
- `debug_checker.py` - Unified testing tool (API, analysis, Slack)
- `zendesk_client.py` - Zendesk API integration
- `ticket_analyzer.py` - OpenAI-powered similarity analysis
- `slack_notifier.py` - Slack webhook notifications
- `sample_tickets.json` - Sample data for testing

## Environment Variables

| Variable               | Required | Default | Description                           |
| ---------------------- | -------- | ------- | ------------------------------------- |
| `ZENDESK_URL`          | Yes      | -       | Your Zendesk instance URL             |
| `ZENDESK_EMAIL`        | Yes      | -       | Your Zendesk email                    |
| `ZENDESK_TOKEN`        | Yes      | -       | Your Zendesk API token                |
| `OPENAI_API_KEY`       | Yes      | -       | OpenAI API key for analysis           |
| `SLACK_WEBHOOK_URL`    | No       | -       | Slack webhook for notifications       |
| `TICKET_CNT_THRESHOLD` | No       | 5       | Minimum tickets to trigger alert      |
| `SEND_TEST_SLACK`      | No       | false   | Send test notifications in debug mode |
