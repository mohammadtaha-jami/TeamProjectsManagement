# استفاده از ایمیج رسمی پایتون به همراه Playwright
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# تنظیم پوشه کاری
WORKDIR /app

# کپی کردن فایل نیازمندی‌ها
COPY requirements.txt .

# نصب پکیج‌های پایتون
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن تمام فایل‌های پروژه
COPY . .

# پورتی که سرور روی آن اجرا می‌شود
EXPOSE 5000

# اجرای برنامه با Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]