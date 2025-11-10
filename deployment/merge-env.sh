#!/usr/bin/env bash
set -euo pipefail

DEPLOY_PATH="${1:-.}"
ENV_FILE="$DEPLOY_PATH/.env"
ENV_EXAMPLE="$DEPLOY_PATH/.env.example"

if [ ! -f "$ENV_EXAMPLE" ] && [ ! -f "$ENV_FILE" ]; then
  echo "⚠️  No .env or .env.example found, skipping merge"
  exit 0
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "📝 Creating .env from .env.example (first deployment)"
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
  else
    touch "$ENV_FILE"
  fi
  exit 0
fi

if [ ! -f "$ENV_EXAMPLE" ]; then
  echo "⚠️  No .env.example found, keeping existing .env"
  exit 0
fi

echo "🔄 Merging .env.example into existing .env..."

declare -A existing_vars
while IFS='=' read -r key value || [ -n "$key" ]; do
  key=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  if [[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]] && [[ ! "$key" =~ ^# ]]; then
    if [ -n "$key" ]; then
      existing_vars["$key"]="$value"
    fi
  fi
done < "$ENV_FILE"

{
  while IFS='=' read -r key value || [ -n "$key" ]; do
    key_trimmed=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
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
    if [ -n "${existing_vars[$key_trimmed]:-}" ]; then
      echo "$key_trimmed=${existing_vars[$key_trimmed]}"
    else
      value_trimmed=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
      echo "$key_trimmed=$value_trimmed"
    fi
  done < "$ENV_EXAMPLE"
} > "$ENV_FILE.tmp"

mv "$ENV_FILE.tmp" "$ENV_FILE"
echo "✅ .env merged successfully (existing values preserved, new keys added)"

