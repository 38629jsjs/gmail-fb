# Use the official Playwright image which has Chrome and Python pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app
COPY . /app

# Install Python dependencies
RUN pip install quart pyTelegramBotAPI playwright

# Install the browser binaries
RUN playwright install chromium

# Run the app
CMD ["python", "app.py"]
