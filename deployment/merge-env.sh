#!/usr/bin/env bash
set -euo pipefail

DEPLOY_PATH="${1:-.}"
ENV_FILE="$DEPLOY_PATH/.env"
ENV_EXAMPLE="$DEPLOY_PATH/.env.example"

# اگر فایل .env.example (که از سیستم شما آمده) وجود ندارد، کاری انجام نده
if [ ! -f "$ENV_EXAMPLE" ]; then
  echo "⚠️  No .env.example found from deployment, keeping existing .env"
  exit 0
fi

# اگر فایل .env برای اولین بار است که ایجاد می‌شود
if [ ! -f "$ENV_FILE" ]; then
  echo "📝 No existing .env found. Creating a new one from deployment file."
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  exit 0
fi

echo "🔄 Updating .env with new values from deployment (.env.example)..."

# --- این بخش منطق کلیدی است ---
# ما یک فایل موقت ایجاد می‌کنیم و تمام متغیرهای فایل جدید (.env.example) را
# با مقادیر جدیدشان در آن می‌نویسیم. این کار تضمین می‌کند که مقادیر شما
# همیشه اولویت دارند و جایگزین مقادیر قدیمی می‌شوند.

{
  # حلقه روی فایل .env.example (که حاوی مقادیر جدید شماست) اجرا می‌شود
  while IFS='=' read -r key value || [ -n "$key" ]; do
    key_trimmed=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    
    # کامنت‌ها و خطوط خالی را رد کن (این بخش از کد شما عالی بود)
    if [[ "$key_trimmed" =~ ^# ]]; then
      echo "$key"
      continue
    fi
    if [[ ! "$key_trimmed" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
      if [ -n "$key" ]; then
        echo "$key"
      fi
      continue
    fi
    if [ -z "$key_trimmed" ]; then
      echo ""
      continue
    fi

    # *** مهمترین تغییر اینجاست ***
    # ما دیگر مقادیر قدیمی را بررسی نمی‌کنیم.
    # به سادگی مقدار جدید را برای هر متغیر می‌نویسیم.
    value_trimmed=$(echo "${value:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    echo "$key_trimmed=$value_trimmed"

  done < "$ENV_EXAMPLE"

} > "$ENV_FILE.tmp" # نتیجه در یک فایل موقت نوشته می‌شود

# فایل موقت را با فایل اصلی جایگزین کن
mv "$ENV_FILE.tmp" "$ENV_FILE"

echo "✅ .env successfully updated with values from the new deployment."