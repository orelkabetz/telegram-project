# Telegram AliExpress Affiliate Bot

A Telegram bot for managing and publishing AliExpress affiliate links to multiple groups.

## Features

- Add AliExpress product links (both direct and affiliate links)
- Store and manage links in a queue
- Publish links to multiple Telegram groups
- Automatic link rotation
- Support for both direct AliExpress URLs and affiliate links

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/telegram-aliexpress-bot.git
cd telegram-aliexpress-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your configuration:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ALIEXPRESS_AFFILIATE_ID=your_aliexpress_affiliate_id
```

4. Run the bot:
```bash
python bot.py
```

## Commands

- `/addlink <url>` - Add a new AliExpress product link
- `/listlinks` - List all stored links
- `/publish` - Publish the next link in the queue to all groups
- `/checklinkdata <url>` - Test scraping functionality for a link
- `/testapi` - Test the connection to AliExpress portal

## Requirements

- Python 3.9+
- python-telegram-bot
- aiohttp
- beautifulsoup4
- python-dotenv

## License

MIT License 