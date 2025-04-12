import os
import logging
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import asyncio
from datetime import datetime, timedelta
import random
import json
import urllib.parse
from collections import deque
import re
import aiohttp
from aliexpress_api import AliexpressApi, models

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# File to store active chats and links
CHATS_FILE = 'active_chats.json'
LINKS_FILE = 'affiliate_links.json'

# Get environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
AFFILIATE_ID = os.getenv('ALIEXPRESS_AFFILIATE_ID')
ALIEXPRESS_API_KEY = os.getenv('ALIEXPRESS_API_KEY')
ALIEXPRESS_API_SECRET = os.getenv('ALIEXPRESS_API_SECRET')

# Initialize AliExpress API
aliexpress = AliexpressApi(
    ALIEXPRESS_API_KEY,
    ALIEXPRESS_API_SECRET,
    models.Language.EN,
    models.Currency.ILS,
    AFFILIATE_ID
)

# Initialize link queue
link_queue = deque()

def load_links():
    """Load affiliate links from file."""
    try:
        if os.path.exists(LINKS_FILE):
            with open(LINKS_FILE, 'r') as f:
                return deque(json.load(f))
        return deque()
    except Exception as e:
        logger.error(f"Error loading links: {e}")
        return deque()

def save_links():
    """Save affiliate links to file."""
    try:
        with open(LINKS_FILE, 'w') as f:
            json.dump(list(link_queue), f)
    except Exception as e:
        logger.error(f"Error saving links: {e}")

# Load existing links on startup
link_queue = load_links()

def load_chats():
    """Load active chats from file."""
    try:
        if os.path.exists(CHATS_FILE):
            with open(CHATS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading chats: {e}")
        return {}

def save_chats(chats):
    """Save active chats to file."""
    try:
        with open(CHATS_FILE, 'w') as f:
            json.dump(chats, f)
    except Exception as e:
        logger.error(f"Error saving chats: {e}")

async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle when bot is added to a new group."""
    chat = update.effective_chat
    if chat.type in ['group', 'supergroup']:
        chats = load_chats()
        chats[str(chat.id)] = chat.title
        save_chats(chats)
        logger.info(f"Added new chat: {chat.title} (ID: {chat.id})")

async def get_chats(bot):
    """Get all active chats from the stored file."""
    chats = load_chats()
    return [(int(chat_id), title) for chat_id, title in chats.items()]

async def extract_product_id(url):
    """Extract product ID from AliExpress URL."""
    try:
        # Extract product ID from URL
        match = re.search(r'item/(\d+)', url)
        if match:
            return match.group(1)
        return None
    except Exception as e:
        logger.error(f"Error extracting product ID: {e}")
        return None

async def fetch_product_details(url):
    """Fetch product details using the AliExpress API."""
    try:
        # Get product details using the API
        products = aliexpress.get_products_details([url])
        if not products:
            logger.error("No product details found")
            return None
            
        product = products[0]
        
        return {
            "title": product.product_title,
            "url": url
        }
    except Exception as e:
        logger.error(f"Error fetching product details: {e}")
        return None

async def generate_affiliate_link(url, tracking_id):
    """Generate an affiliate link using the AliExpress API."""
    try:
        # Get affiliate link using the API
        affiliate_links = aliexpress.get_affiliate_links(url)
        if not affiliate_links:
            logger.error("No affiliate links generated")
            return None
            
        # Return the first promotion link
        return affiliate_links[0].promotion_link
    except Exception as e:
        logger.error(f"Error generating affiliate link: {e}")
        return None

async def handle_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /addlink command to add a new affiliate link."""
    chat = update.effective_chat
    if chat.type != 'private':
        await update.message.reply_text("❌ פקודה זו זמינה רק בצ'אט פרטי")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ אנא הזן את קישור המוצר מאליאקספרס\n\n"
            "דוגמה:\n"
            "/addlink https://www.aliexpress.com/item/1005005051234567.html"
        )
        return

    try:
        # Get the URL from the command
        url = context.args[0]
        
        # Extract product ID
        await update.message.reply_text("⏳ מאתר מזהה המוצר...")
        product_id = await extract_product_id(url)
        if not product_id:
            await update.message.reply_text("❌ לא ניתן למצוא את מזהה המוצר בקישור")
            return
        
        # Fetch product details
        await update.message.reply_text("⏳ מאתר פרטי המוצר...")
        product_details = await fetch_product_details(url)
        
        if not product_details:
            await update.message.reply_text("❌ לא ניתן לאתר את פרטי המוצר")
            return
        
        # Generate affiliate link
        await update.message.reply_text("⏳ מייצר קישור שותפים...")
        affiliate_link = await generate_affiliate_link(url, AFFILIATE_ID)
        
        if not affiliate_link:
            await update.message.reply_text("❌ לא ניתן לייצר קישור שותפים")
            return
        
        # Create a new link entry
        new_link = {
            "title": product_details["title"],
            "product_id": product_id,
            "url": url,
            "affiliate_link": affiliate_link
        }

        # Add to queue
        link_queue.append(new_link)
        save_links()

        # Send confirmation
        await update.message.reply_text(
            "✅ קישור חדש נוסף בהצלחה!\n\n"
            f"כותרת: {product_details['title']}\n\n"
            f"קישור שותפים: {affiliate_link}"
        )
    except Exception as e:
        logger.error(f"Error adding link: {e}")
        await update.message.reply_text("❌ אירעה שגיאה בהוספת הקישור")

async def handle_list_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /listlinks command to show all stored links."""
    chat = update.effective_chat
    if chat.type != 'private':
        await update.message.reply_text("❌ פקודה זו זמינה רק בצ'אט פרטי")
        return

    if not link_queue:
        await update.message.reply_text("❌ אין קישורים שמורים")
        return

    message = "📋 רשימת הקישורים השמורים:\n\n"
    for i, link in enumerate(link_queue, 1):
        message += (
            f"{i}. {link['title']}\n"
            f"   קישור שותפים: {link['affiliate_link']}\n\n"
        )

    await update.message.reply_text(message)

async def handle_clear_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /clearlinks command to clear all stored links."""
    chat = update.effective_chat
    if chat.type != 'private':
        await update.message.reply_text("❌ פקודה זו זמינה רק בצ'אט פרטי")
        return

    link_queue.clear()
    save_links()
    await update.message.reply_text("✅ כל הקישורים נמחקו בהצלחה")

async def send_deal_to_chat(bot, chat_id, chat_title):
    """Send a deal with affiliate link to a specific chat."""
    try:
        if not link_queue:
            logger.warning("No links available in queue")
            return

        # Get the next link from the queue and remove it
        deal = link_queue.popleft()
        save_links()

        message = (
            f"🔥 {deal['title']}\n\n"
            f"🛒 קישור למוצר: {deal['affiliate_link']}"
        )
        await bot.send_message(
            chat_id=chat_id,
            text=message
        )
        logger.info(f"Sent deal to {chat_title} (ID: {chat_id})")
    except Exception as e:
        logger.error(f"Error sending deal to {chat_title}: {e}")

async def send_deals_to_all(bot, chats):
    """Send deals to all group chats."""
    for chat_id, chat_title in chats:
        await send_deal_to_chat(bot, chat_id, chat_title)

async def handle_publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /publish command."""
    chat = update.effective_chat
    bot = context.bot
    
    if chat.type == 'private':
        # If command is used in private chat, send deals to all groups
        try:
            chats = await get_chats(bot)
            if chats:
                await send_deals_to_all(bot, chats)
                await update.message.reply_text("✅ נשלחו קישורים לכל הקבוצות!")
            else:
                await update.message.reply_text("❌ לא נמצאו קבוצות פעילות")
        except Exception as e:
            logger.error(f"Error sending deals to all groups: {e}")
            await update.message.reply_text("❌ אירעה שגיאה בשליחת הקישורים")
    else:
        # If command is used in a group, send deal only to that group
        await send_deal_to_chat(bot, chat.id, chat.title)

async def scheduled_deals(context: ContextTypes.DEFAULT_TYPE):
    """Send deals on schedule."""
    try:
        bot = context.bot
        chats = await get_chats(bot)
        if chats:
            await send_deals_to_all(bot, chats)
            logger.info("Successfully sent scheduled deals")
        else:
            logger.info("No chats found for scheduled deals")
    except Exception as e:
        logger.error(f"Error in scheduled deals: {e}")

async def test_api_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test the connection to AliExpress API."""
    chat = update.effective_chat
    if chat.type != 'private':
        await update.message.reply_text("❌ פקודה זו זמינה רק בצ'אט פרטי")
        return

    try:
        # Test URL (a simple product URL)
        test_url = "https://www.aliexpress.com/item/1005005051234567.html"
        
        # Show what we're testing
        await update.message.reply_text(
            "🔍 בודק חיבור ל-API של אליאקספרס...\n\n"
            f"URL: {test_url}\n"
            f"Tracking ID: {AFFILIATE_ID}"
        )

        # Try to fetch product details
        product_details = await fetch_product_details(test_url)
        
        if product_details:
            # Try to generate an affiliate link
            affiliate_link = await generate_affiliate_link(test_url, AFFILIATE_ID)
            
            if affiliate_link:
                await update.message.reply_text(
                    "✅ החיבור ל-API עובד בהצלחה!\n\n"
                    f"כותרת המוצר: {product_details['title']}\n"
                    f"קישור שותפים: {affiliate_link}"
                )
            else:
                await update.message.reply_text(
                    "⚠️ ניתן לאתר פרטי מוצר אך לא ניתן לייצר קישור שותפים\n\n"
                    "אנא וודא שמזהה המעקב (Tracking ID) נכון"
                )
        else:
            await update.message.reply_text(
                "❌ לא ניתן להתחבר ל-API\n\n"
                "אנא וודא שהמפתחות (API Key ו-API Secret) נכונים"
            )

    except Exception as e:
        logger.error(f"Error testing API connection: {e}")
        await update.message.reply_text(f"❌ שגיאה בבדיקת החיבור: {str(e)}")

def main():
    """Main function to run the bot."""
    # Create the Application with job queue
    application = (
        Application.builder()
        .token(os.getenv('TELEGRAM_BOT_TOKEN'))
        .concurrent_updates(True)
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler("publish", handle_publish_command))
    application.add_handler(CommandHandler("addlink", handle_add_link))
    application.add_handler(CommandHandler("listlinks", handle_list_links))
    application.add_handler(CommandHandler("clearlinks", handle_clear_links))
    application.add_handler(CommandHandler("testapi", test_api_connection))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    
    # Schedule deals to be sent every 4 hours
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(scheduled_deals, interval=timedelta(hours=4), first=0)
        logger.info("Scheduled job started successfully")
    else:
        logger.error("Job queue not available")
    
    # Start the bot
    logger.info("Starting bot...")
    
    # Run the bot until Ctrl+C is pressed
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error in main: {e}") 