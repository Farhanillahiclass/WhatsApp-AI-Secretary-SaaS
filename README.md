# WhatsApp AI Secretary SaaS

A Flask-based WhatsApp automation platform using the official WhatsApp Cloud API. Create keyword-based auto-reply rules and manage conversations through a web dashboard.

## Features

- User authentication (register/login)
- Keyword-based auto-reply rules
- Multiple match types (exact, contains, starts_with)
- Real-time webhook handling
- Message logging and analytics
- Responsive web dashboard

## Quick Start

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your WhatsApp API credentials
4. Run: `python app.py`
5. Visit: `http://localhost:5000`

## WhatsApp Cloud API Setup

1. Create a Meta Developer account at https://developers.facebook.com
2. Create a WhatsApp Business App
3. Get your Access Token, Phone Number ID, and Business Account ID
4. Configure webhook URL in Meta Dashboard
5. Start automating!

## Environment Variables

| Variable | Description |
|----------|-------------|
| SECRET_KEY | Flask secret key |
| WHATSAPP_API_TOKEN | Meta API access token |
| WHATSAPP_PHONE_NUMBER_ID | Your WhatsApp phone number ID |
| WHATSAPP_VERIFY_TOKEN | Custom token for webhook verification |

## License

MIT