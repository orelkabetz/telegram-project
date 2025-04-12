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
import requests
from bs4 import BeautifulSoup
import aiohttp

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

# Get affiliate ID and API key from environment
AFFILIATE_ID = os.getenv('ALIEXPRESS_AFFILIATE_ID')
API_KEY = os.getenv('ALIEXPRESS_API_KEY')

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

def create_affiliate_link(product_id):
    """Create an AliExpress affiliate link."""
    base_url = "https://s.click.aliexpress.com/e/_"
    params = {
        "aff_platform": "default",
        "aff_trace_key": AFFILIATE_ID,
        "item_id": product_id
    }
    return f"{base_url}{urllib.parse.quote_plus(str(params))}"

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
    """Extract product ID from AliExpress URL, handling both direct and affiliate links."""
    try:
        # If it's a direct AliExpress URL, extract the ID directly
        if 'aliexpress.com/item/' in url:
            match = re.search(r'item/(\d+)', url)
            if match:
                return match.group(1)
            return None

        # For affiliate links, we need to follow the redirect
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                if response.status != 200:
                    logger.error(f"Failed to follow redirect. Status: {response.status}")
                    return None
                
                # Get the final URL after all redirects
                final_url = str(response.url)
                logger.info(f"Final URL after redirects: {final_url}")
                
                # Extract product ID from the final URL
                match = re.search(r'item/(\d+)', final_url)
                if match:
                    return match.group(1)
                
                return None
    except Exception as e:
        logger.error(f"Error extracting product ID: {e}")
        return None

async def fetch_product_details(url):
    """Fetch product title from AliExpress URL."""
    try:
        # Headers for the request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch product page. Status: {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Try to find title in meta tags first (most reliable)
                meta_title = soup.find('meta', property='og:title')
                if meta_title:
                    title = meta_title.get('content', '').strip()
                    logger.info(f"Found title in meta tag: {title}")
                    return {
                        "title": title,
                        "url": url
                    }
                
                # Fallback to other title selectors
                title_selectors = [
                    'h1.product-title',
                    'div.product-title',
                    'h1[data-spm-anchor-id]',
                    'div[data-spm-anchor-id]',
                    'h1.title',
                    'div.title',
                    'h1.product-name',
                    'div.product-name'
                ]
                
                for selector in title_selectors:
                    title_elem = soup.select_one(selector)
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        logger.info(f"Found title using selector '{selector}': {title}")
                        return {
                            "title": title,
                            "url": url
                        }
                
                logger.error("Could not find product title")
                return None
    except Exception as e:
        logger.error(f"Error fetching product details: {e}")
        return None

async def generate_affiliate_link(url, tracking_id):
    """Generate affiliate link using AliExpress portal link generator format."""
    try:
        # Extract product ID from URL
        product_id = extract_product_id(url)
        if not product_id:
            return None

        # Create the affiliate link using the portal's format
        base_url = "https://portals.aliexpress.com/affiportals/web/link_generator.htm"
        params = {
            "spm": "0._cps_dada.0.0.409c5Mcj5Mcj8U",
            "itemId": product_id,
            "trackingId": tracking_id
        }
        
        # URL encode the parameters
        encoded_params = urllib.parse.urlencode(params)
        affiliate_link = f"{base_url}?{encoded_params}"
        
        return affiliate_link
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
        
        # Extract product ID (now async)
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
        
        # Create a new link entry
        new_link = {
            "title": product_details["title"],
            "product_id": product_id,
            "url": url,
            "affiliate_link": url  # Using the original URL as affiliate link for now
        }

        # Add to queue
        link_queue.append(new_link)
        save_links()

        # Send confirmation
        await update.message.reply_text(
            "✅ קישור חדש נוסף בהצלחה!\n\n"
            f"כותרת: {product_details['title']}\n\n"
            f"קישור: {url}"
        )
    except Exception as e:
        logger.error(f"Error adding link: {e}")
        await update.message.reply_text("❌ אירעה שגיאה בהוספת הקישור")

async def handle_update_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /updatelink command to update link details."""
    chat = update.effective_chat
    if chat.type != 'private':
        await update.message.reply_text("❌ פקודה זו זמינה רק בצ'אט פרטי")
        return

    if len(context.args) < 5:
        await update.message.reply_text(
            "❌ אנא הזן את פרטי המוצר בפורמט הבא:\n"
            "/updatelink <מספר> <כותרת> <מחיר> <מחיר מקורי> <הנחה>\n\n"
            "דוגמה:\n"
            "/updatelink 1 🎮 משחק מחשב 49.99 199.99 75%"
        )
        return

    try:
        index = int(context.args[0]) - 1
        if index < 0 or index >= len(link_queue):
            await update.message.reply_text("❌ מספר קישור לא תקין")
            return

        title = context.args[1]
        price = f"₪{context.args[2]}"
        original_price = f"₪{context.args[3]}"
        discount = f"{context.args[4]}%"

        # Update the link details
        link = link_queue[index]
        link.update({
            "title": title,
            "price": price,
            "original_price": original_price,
            "discount": discount
        })
        save_links()

        await update.message.reply_text(
            "✅ פרטי המוצר עודכנו בהצלחה!\n\n"
            f"כותרת: {title}\n"
            f"מחיר: {price}\n"
            f"מחיר מקורי: {original_price}\n"
            f"הנחה: {discount}"
        )
    except Exception as e:
        logger.error(f"Error updating link: {e}")
        await update.message.reply_text("❌ אירעה שגיאה בעדכון פרטי המוצר")

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

async def send_sample_deal_to_chat(bot, chat_id, chat_title):
    """Send a sample deal to a specific chat (keep existing)."""
    try:
        deal = random.choice(SAMPLE_DEALS)
        message = (
            f"🔥 {deal['title']}\n\n"
            f"💰 מחיר: {deal['price']}\n"
            f"📉 מחיר מקורי: {deal['original_price']}\n"
            f"🎯 הנחה: {deal['discount']}\n\n"
            f"🛒 קישור למוצר: {deal['url']}"
        )
        await bot.send_message(
            chat_id=chat_id,
            text=message
        )
        logger.info(f"Sent sample deal to {chat_title} (ID: {chat_id})")
    except Exception as e:
        logger.error(f"Error sending sample deal to {chat_title}: {e}")

async def send_real_deal_to_chat(bot, chat_id, chat_title):
    """Send a real deal with affiliate link to a specific chat."""
    try:
        if not link_queue:
            logger.warning("No links available in queue")
            return

        # Get the next link from the queue and remove it
        deal = link_queue.popleft()  # Use popleft() to remove from the beginning
        save_links()

        message = (
            f"🔥 {deal['title']}\n\n"
            f"🛒 קישור למוצר: {deal['affiliate_link']}"
        )
        await bot.send_message(
            chat_id=chat_id,
            text=message
        )
        logger.info(f"Sent real deal to {chat_title} (ID: {chat_id})")
    except Exception as e:
        logger.error(f"Error sending real deal to {chat_title}: {e}")

async def send_sample_deals_to_all(bot, chats):
    """Send sample deals to all group chats (keep existing)."""
    for chat_id, chat_title in chats:
        await send_sample_deal_to_chat(bot, chat_id, chat_title)

async def send_real_deals_to_all(bot, chats):
    """Send real deals to all group chats (new)."""
    for chat_id, chat_title in chats:
        await send_real_deal_to_chat(bot, chat_id, chat_title)

async def handle_publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /publish command."""
    chat = update.effective_chat
    bot = context.bot
    
    if chat.type == 'private':
        # If command is used in private chat, send deals to all groups
        try:
            chats = await get_chats(bot)
            if chats:
                await send_real_deals_to_all(bot, chats)  # Use real deals
                await update.message.reply_text("✅ נשלחו קישורים לכל הקבוצות!")
            else:
                await update.message.reply_text("❌ לא נמצאו קבוצות פעילות")
        except Exception as e:
            logger.error(f"Error sending deals to all groups: {e}")
            await update.message.reply_text("❌ אירעה שגיאה בשליחת הקישורים")
    else:
        # If command is used in a group, send deal only to that group
        await send_real_deal_to_chat(bot, chat.id, chat.title)  # Use real deals

async def scheduled_deals(context: ContextTypes.DEFAULT_TYPE):
    """Send deals on schedule."""
    try:
        bot = context.bot
        chats = await get_chats(bot)
        if chats:
            await send_real_deals_to_all(bot, chats)  # Use real deals
            logger.info("Successfully sent scheduled deals")
        else:
            logger.info("No chats found for scheduled deals")
    except Exception as e:
        logger.error(f"Error in scheduled deals: {e}")

async def test_api_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test the connection to AliExpress portal link generator."""
    chat = update.effective_chat
    if chat.type != 'private':
        await update.message.reply_text("❌ פקודה זו זמינה רק בצ'אט פרטי")
        return

    try:
        # Test URL (a simple product URL)
        test_url = "https://www.aliexpress.com/item/1005005051234567.html"
        
        # Show what we're testing
        await update.message.reply_text(
            "🔍 בודק חיבור למחולל הקישורים...\n\n"
            f"URL: {test_url}\n"
            f"Tracking ID: {AFFILIATE_ID}"
        )

        # Try to generate an affiliate link
        affiliate_link = await generate_affiliate_link(test_url, AFFILIATE_ID)
        
        if affiliate_link:
            await update.message.reply_text(
                "✅ קישור שותפים נוצר בהצלחה!\n\n"
                f"קישור מקורי: {test_url}\n"
                f"קישור למחולל: {affiliate_link}\n\n"
                "ℹ️ הערה: יש ללחוץ על הקישור ולבחור 'Generate Link' במחולל הקישורים"
            )
        else:
            await update.message.reply_text(
                "❌ לא ניתן לייצר קישור שותפים\n\n"
                "אנא וודא שהקישור תקין ושמזהה המעקב (Tracking ID) נכון"
            )

    except Exception as e:
        logger.error(f"Error testing connection: {e}")
        await update.message.reply_text(f"❌ שגיאה בבדיקת החיבור: {str(e)}")

async def handle_check_link_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /checklinkdata command to test scraping functionality."""
    chat = update.effective_chat
    if chat.type != 'private':
        await update.message.reply_text("❌ פקודה זו זמינה רק בצ'אט פרטי")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ אנא הזן את קישור המוצר מאליאקספרס\n\n"
            "דוגמה:\n"
            "/checklinkdata https://www.aliexpress.com/item/1005005051234567.html"
        )
        return

    try:
        url = context.args[0]
        await update.message.reply_text("⏳ סורק את פרטי המוצר...")
        
        # Fetch product details
        product_details = await fetch_product_details(url)
        
        if product_details:
            message = (
                "✅ פרטי המוצר אותרו בהצלחה!\n\n"
                f"📝 כותרת: {product_details['title']}\n"
                f"🔗 קישור מקורי: {url}"
            )
        else:
            message = (
                "❌ לא ניתן לאתר את פרטי המוצר\n\n"
                "אנא וודא שהקישור תקין וניתן לגשת אליו"
            )
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error checking link data: {e}")
        await update.message.reply_text(f"❌ שגיאה בבדיקת פרטי המוצר: {str(e)}")

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
    application.add_handler(CommandHandler("updatelink", handle_update_link))
    application.add_handler(CommandHandler("listlinks", handle_list_links))
    application.add_handler(CommandHandler("clearlinks", handle_clear_links))
    application.add_handler(CommandHandler("testapi", test_api_connection))
    application.add_handler(CommandHandler("checklinkdata", handle_check_link_data))
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