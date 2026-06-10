# ═══════════════════════════════════════════════
#   SER Platform — Configuration
#   املئي هذا الملف ببياناتك الحقيقية
# ═══════════════════════════════════════════════

# ── Gmail SMTP ──────────────────────────────────
# 1. فعّلي 2-Step Verification في حسابك
# 2. ابحثي عن "App passwords" في إعدادات الأمان
# 3. أنشئي App Password وضعيه هنا (16 حرف بدون مسافات)
GMAIL_USER     = "your_email@gmail.com"
GMAIL_PASSWORD = "abcdefghijklmnop"   # App Password (16 chars, no spaces)

# ── Twilio SMS ──────────────────────────────────
# سجّلي مجاناً على twilio.com
# ستجدين Account SID و Auth Token في الـ Dashboard
TWILIO_SID   = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TWILIO_TOKEN = "your_auth_token_here"
TWILIO_FROM  = "+1XXXXXXXXXX"   # رقم Twilio المجاني
