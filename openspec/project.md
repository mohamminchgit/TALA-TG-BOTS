# Project Context

## Purpose
The purpose of this project is to build a Telegram arbitrage bot for trading between Telegram trading groups. By utilizing two agents (Userbots) in a source and a destination group, and a central decision-making engine, the bot will identify profitable opportunities and automatically execute buy and sell trades at high speed. The primary goal is to profit from the price spread between the two groups through advanced risk management.


--------------------------------------------
## Tech Stack
- **Python 3.11 (CPython)**: Core runtime for agents, engine, and admin bot. The Docker image upgrades to Python 3.11 while local development remains compatible with Python 3.10+.
- **Telethon**: Telegram client framework that powers userbot logins, message parsing, and command execution for both trading groups.
- **Redis 7**: Pub/Sub transport and transient cache for cross-component messaging. Runs as a sidecar container in the Docker Compose deployment.
- **SQLite 3**: Embedded relational database for persistent configuration, trade history, and performance metrics. Stored on a bind-mounted volume so data survives container rebuilds.
- **Docker & Docker Compose v2**: Container orchestration used on the Linux server. The Compose file builds the app image, provisions Redis, mounts persistent volumes, and enforces always-on restart policies.
- **PowerShell 7 + OpenSSH (Windows)**: Used to package the repository, transfer it over SSH, and trigger `docker compose up -d --build` remotely through the `deployment/deploy.ps1` script.
- **GNU Bash**: Entry point runtime inside the container. The `deployment/docker-entrypoint.sh` supervisor script launches the engine and agent processes together and handles shutdown signals.
--------------------------------------------

## Project Conventions

## 1. Project Structure
```
project/
│
├─ src/
│   ├─ bot_agent/
│   │   ├─ handlers/
│   │   ├─ services/
│   │   └─ main.py
│   │
│   ├─ engine/
│   │   ├─ core/
│   │   ├─ models/
│   │   ├─ services/
│   │   └─ main.py
│   │
│   ├─ common/
│   │   ├─ 
│   │   ├─ db.py
│   │   └─ schemas.py
│   │
│   ├─ config/
│   │   ├─ __init__.py
│   │   └─ settings.py
│
├─ data/
│   └─ database.db
│
├─ sessions/
│   ├─ source.session
│   └─ destination.session
│
├─ scripts/
│   ├─ generate_session.py
│   ├─ publish_execution_result.py
│   ├─ send_admin_command.py
│   └─ simulate_arbitrage.py
│
├─ deployment/
│   ├─ docker-compose.yml
│   ├─ docker-entrypoint.sh
│   ├─ deploy.ps1
│   └─ restart.ps1
│
├─ .dockerignore
├─ Dockerfile
├─ requirements.txt
├─ .env
└─ README.md
```

----#

## 2. Code Style & Quality

### **2.1. Code Formatting & Standards**
- **Python Version:** Python 3.10+
- **Style Guide:** Follow PEP 8 conventions strictly
- **Linter:** Use `flake8` or `pylint` for code quality checks
- **Formatter:** Use `black` for automatic code formatting (line length: 120)
- **Type Hints:** Mandatory for all function signatures and class methods
- **Import Order:** 
  1. Standard library imports
  2. Third-party imports (Telethon, Redis, etc.)
  3. Local application imports

### **2.2. Naming Conventions**
- **Variables & Functions:** `snake_case` (e.g., `calculate_profit_spread`, `order_book`)
- **Classes:** `PascalCase` (e.g., `ArbitrageEngine`, `TelegramAgent`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `MINIMUM_PROFIT_SPREAD`, `REDIS_HOST`)
- **Private Methods:** Prefix with single underscore `_method_name`
- **Redis Channels:** `snake_case` with descriptive names (e.g., `group_events`, `execution_commands`)

### **2.3. Documentation Standards**
- **Docstrings:** Required for all classes, functions, and modules using Google-style format
- **Comments:** Explain "why" not "what" - code should be self-explanatory
- **Type Annotations:** Use Python's `typing` module for complex types

```python
from typing import Dict, Optional, List

def process_trade(
    trade_id: str, 
    quantity: int, 
    price: float
) -> Dict[str, any]:
    """
    Process a trade execution and return result.
    
    Args:
        trade_id: Unique identifier for the trade
        quantity: Number of units to trade
        price: Price per unit
        
    Returns:
        Dictionary containing trade status and details
    """
    pass
```

### **2.4. Error Handling**
- **Never use bare `except` clauses** - always specify exception types
- **Custom Exceptions:** Define domain-specific exceptions in `common/exceptions.py`
- **Logging:** Use Python's `logging` module with appropriate levels:
  - `DEBUG`: Detailed diagnostic information
  - `INFO`: General operational events
  - `WARNING`: Non-critical issues (e.g., reconciliation discrepancies)
  - `ERROR`: Serious issues (e.g., failed trade execution)
  - `CRITICAL`: System-level failures (e.g., Redis connection loss)

### **2.5. Async/Await Patterns**
- Use `asyncio` for all Telethon operations and Redis Pub/Sub
- Avoid blocking operations in async contexts
- Use `asyncio.gather()` for parallel operations when safe

### **2.6. Configuration Management**
- **Environment Variables:** Store sensitive data (API credentials, phone numbers) in `.env`
- **Config Files:** Store operational parameters in SQLite (`config.db`)
- **Never commit** `.env` or session files to version control
- **Telegram Sessions:** Each agent MUST use a distinct Telethon session file to avoid SQLite locks.
  - `SOURCE_SESSION_FILE` (example: `sessions/source.session`)
  - `DESTINATION_SESSION_FILE` (example: `sessions/destination.session`)
  - If both resolve to the same path, startup fails with a clear error.

### **2.7. Git Workflow**
- **Branches:** 
  - `main` - Production-ready code
  - `develop` - Integration branch
  - `feature/*` - New features
  - `hotfix/*` - Urgent fixes
- **Commit Messages:** Use conventional commits format:
  - `feat:` - New feature
  - `fix:` - Bug fix
  - `refactor:` - Code restructuring
  - `docs:` - Documentation changes
  - `test:` - Test-related changes

---

## 3. File & Module Organization

### **3.1. Module Responsibilities**

#### **bot_agent/**
- **Purpose:** Telegram interaction layer for both Bot A and Bot B
- **handlers/:** Event handlers for incoming Telegram messages
  - `message_handler.py` - Parse and classify incoming messages
  - `event_publisher.py` - Publish events to Redis
- **services/:**
  - `telegram_service.py` - Wrapper for Telethon client operations
  - `command_executor.py` - Execute commands from Redis (reply, post, cancel)
- **main.py:** Entry point, connects to Telegram and Redis, starts event loop

#### **engine/**
- **Purpose:** Central decision-making and orchestration
- **core/:**
  - `arbitrage_engine.py` - Main orchestration logic
  - `order_book.py` - In-memory order book management
  - `trade_matcher.py` - Immediate arbitrage opportunity detection
  - `market_maker.py` - Predictive market-making strategy
- **models/:**
  - `order.py` - Order data model
  - `trade.py` - Trade data model
  - `config.py` - Configuration model
- **services/:**
  - `risk_manager.py` - Exit strategies and circuit breaker
  - `redis_service.py` - Redis Pub/Sub and caching operations
  - `db_service.py` - SQLite read/write operations
  - `reconciliation_service.py` - Periodic state synchronization
- **main.py:** Entry point, starts engine and background tasks

#### **common/**
- **db.py:** SQLite connection and schema definitions
- **schemas.py:** Pydantic models for data validation
- **exceptions.py:** Custom exception classes
- **utils.py:** Shared utility functions (Persian number conversion, etc.)
- **constants.py:** Shared constants across modules

#### **config/**
- **settings.py:** Load and validate environment variables and configurations

---

## 4. Redis Data Structure

### **4.1. Pub/Sub Channels**
- **`group_events`:** Bot A/B → Engine (order updates, cancellations, market price)
- **`execution_commands`:** Engine → Bot A/B (trade commands)
- **`execution_results`:** Bot A/B → Engine (success/failure reports)
- **`admin_commands`:** Admin Bot → Engine (config updates, panic button)
- **`admin_reports`:** Engine → Admin Bot (alerts, statistics)

### **4.2. Data Stores (Keys)**
- **`orderbook:source`:** Hash - Current orders in source group
- **`orderbook:destination`:** Hash - Current orders in destination group
- **`executed_trades_cache`:** Set - MessageIDs of executed trades (TTL: 1 hour)
- **`pending_trades:{trade_id}`:** Hash - State of active trades (TTL: 5 minutes)
- **`engine_status`:** String - Current engine state (active/paused/halted)

---

## 5. Database Schema (SQLite)

### **5.1. Tables**

#### **config**
```sql
CREATE TABLE config (
    parameter_name TEXT PRIMARY KEY,
    parameter_value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### **trade_history**
```sql
CREATE TABLE trade_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT UNIQUE NOT NULL,
    strategy TEXT NOT NULL, -- 'immediate' or 'predictive'
    source_message_id INTEGER,
    destination_message_id INTEGER,
    quantity INTEGER NOT NULL,
    source_price REAL NOT NULL,
    destination_price REAL NOT NULL,
    profit REAL NOT NULL,
    status TEXT NOT NULL, -- 'success', 'emergency_exit', 'failed'
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### **performance_stats**
```sql
CREATE TABLE performance_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    successful_trades INTEGER DEFAULT 0,
    emergency_exits INTEGER DEFAULT 0,
    total_profit REAL DEFAULT 0.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);
```

#### **alert_log**
```sql
CREATE TABLE alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL, -- 'service_outage', 'emergency_exit', 'error'
    message TEXT NOT NULL,
    severity TEXT NOT NULL, -- 'info', 'warning', 'critical'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. Message Parsing & Regex Patterns

### **6.1. Order Detection Patterns**
```python
# Buy order: 🔵 [alias] [qty] خ [price]
BUY_ORDER_PATTERN = r'🔵\s+(\S+)\s+([۰-۹0-9]+)\s+خ\s+([۰-۹0-9]+)'

# Sell order: 🔴 [alias] [qty] ف [price]
SELL_ORDER_PATTERN = r'🔴\s+(\S+)\s+([۰-۹0-9]+)\s+ف\s+([۰-۹0-9]+)'

# Market price: 🟡 مظنه: [price] 🟡
MARKET_PRICE_PATTERN = r'🟡\s*مظنه:\s*([۰-۹0-9]+)\s*🟡'

# Trade confirmation
TRADE_CONFIRMATION_PATTERN = r'🔵\s*خریدار\s*:\s*(\S+).*🔴\s*فروشنده\s*:\s*(\S+).*تعداد:\s*([۰-۹0-9]+)\s*قیمت:([۰-۹0-9,]+)'
```

### **6.2. Persian Number Conversion**
```python
PERSIAN_TO_ENGLISH = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')

def normalize_persian_numbers(text: str) -> str:
    """Convert Persian digits to English digits."""
    return text.translate(PERSIAN_TO_ENGLISH)
```

---

#### **Implementation Steps:**

**1. Generate the Session String:**
Create a temporary local script named `generate_session.py` to produce the session string.

### Testing Strategy

The approach is to avoid writing any unit tests. Instead, the bot will be implemented in a way that it is fully runnable at the end of each development stage, with its databases fully functional. This will allow us to conduct step-by-step End-to-End testing, and I will provide feedback based on the results.


## 7. Deployment & Runtime Operations

### 7.1 Container Topology
- The Compose definition lives at `deployment/docker-compose.yml`. It builds a single application image from the root `Dockerfile` and provisions a companion `redis:7-alpine` container. Redis exposes no ports externally; the Python services reach it through the internal Docker network using the hostname `redis`.
- The `arbitrage-bot` service binds `../data` and `../sessions` into `/app/data` and `/app/sessions`, so SQLite databases and Telethon session files persist across rebuilds.
- Both services declare `restart: unless-stopped`, so the Docker daemon automatically restarts them if the host reboots or the process exits unexpectedly.

### 7.2 Entry Point Supervisor
- The `deployment/docker-entrypoint.sh` script runs inside the container. In its default `RUN_MODE=all`, it launches `python main.py engine` and `python main.py run` in parallel, tracks both process IDs, and propagates shutdown signals so they stop cleanly.
- You can override the behavior per container by exporting `RUN_MODE=engine` or `RUN_MODE=agents` in `docker-compose.yml` (useful for advanced diagnostics).
- The script is POSIX-compatible Bash and ships with the image; it is marked executable in the Docker build stage.

### 7.3 Persistent Secrets and State
- The server keeps its own copy of `.env`, `data/`, and `sessions/`. The deploy script purposely excludes these paths from the archive so that production secrets are never overwritten by local development values.
- On the first installation, manually copy `.env` and both `sessions/*.session` files to the server directory before running `docker compose up`. Afterwards, Telethon will reuse those session files even when the container is rebuilt.
- SQLite locking works correctly with the bind mount because the directory is shared in full; avoid mapping just the database file.
  
Recommended `.env` excerpt:
```
SOURCE_SESSION_FILE=sessions/source.session
DESTINATION_SESSION_FILE=sessions/destination.session
```

### 7.4 One-Command Remote Deploy from Windows
- Prerequisites: install the Windows OpenSSH client, ensure `ssh`, `scp`, and `tar` are available in PowerShell, and provision Docker Engine + Compose v2 on the Linux host.
- Configure environment variables once in your PowerShell profile:
  - `TALATG_DEPLOY_HOST` → server host or IP (e.g., `bot.example.com`)
  - `TALATG_DEPLOY_USER` → SSH username with rights to run Docker
  - `TALATG_DEPLOY_PATH` → directory on the server (e.g., `/opt/talatg`)
- Run the deployment script after committing local changes:
  ```
  pwsh -ExecutionPolicy Bypass -File deployment/deploy.ps1 `
    -targetHost "rbot-server" `
    -User "gold" `
    -RemotePath "/home/gold/my-arbitrage-bot"
  ```
- Pass the three parameters inline whenever your shell profile is not pre-loading them. The script performs these steps atomically for you:
  1. Creates a timestamped `tar.gz` archive of the repository while excluding secrets, sessions, and build artefacts.
  2. Copies the archive to `/tmp` on the server via `scp`.
  3. SSHes into the host, extracts the archive into `$TALATG_DEPLOY_PATH`, and executes `docker compose up -d --build`.
  4. Cleans up the temporary archive locally and remotely.
- Because Compose rebuilds the image in-place and uses persistent volumes, the service comes back with the latest code while keeping runtime state.

### 7.5 Automated CI/CD Deployment (GitHub Actions)
- **Automatic deployment on `develop` branch push:** When you push code to the `develop` branch, GitHub Actions automatically deploys it to your Linux server without manual intervention.
- **Setup (one-time):**
  1. Go to your GitHub repository → Settings → Secrets and variables → Actions
  2. Add these secrets:
     - `DEPLOY_HOST`: Your server hostname or IP (e.g., `185.73.113.173` or `rbot-server`)
     - `DEPLOY_USER`: SSH username (e.g., `gold`)
     - `DEPLOY_PORT`: SSH port (e.g., `2233`, or omit for default `22`)
     - `DEPLOY_SSH_KEY`: Your private SSH key content (the entire key, including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`)
     - `DEPLOY_PATH`: Server deployment directory (e.g., `/home/gold/my-arbitrage-bot`)
  3. Create a `.env.example` file in the repository root with all required environment variables (without sensitive values). This serves as a template that gets merged with the server's existing `.env` during deployment.
- **How it works:**
  1. You push to `develop` branch
  2. The workflow validates that all deployment secrets (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH`) are present
  2. GitHub Actions creates a deployment archive (excluding `.env`, `data/`, `sessions/`)
  3. Archives the code and uploads it to the server via SSH
  4. Extracts the archive on the server
  5. Runs `deployment/merge-env.sh` to merge `.env.example` with the existing `.env` (preserving existing values, adding new keys)
  6. Preserves `sessions/` directory (never overwrites session files)
  7. Executes `docker compose up -d --build` to rebuild and restart containers
  8. Cleans up temporary files
  9. Invokes `python3 scripts/admin_notify.py` on the server so the admin bot broadcasts deployment status (success/failure, commit author, and summary)
- **Workflow file:** `.github/workflows/deploy-develop.yml` defines the automation. You can view deployment status in the GitHub Actions tab.
- **Session files protection:** The workflow explicitly excludes `sessions/` from the archive, so your Telethon session files are never overwritten. Only code changes are deployed.
- **Environment variable merging:** The `deployment/merge-env.sh` script intelligently merges `.env.example` (from the repository) with the server's existing `.env`:
  - Existing keys in `.env` are preserved (your production secrets stay intact)
  - New keys from `.env.example` are added (new configuration options are automatically available)
  - Comments and formatting from `.env.example` are maintained
- **Admin notifications:** Deployment status (started, success, failure) appears automatically in the admin Telegram panel; commit hash, author, and title are included for quick reviews.
- **Quick setup checklist:**
  1. Generate or copy your SSH private key (the one you use to connect to `rbot-server`)
  2. In GitHub: Repository → Settings → Secrets and variables → Actions → New repository secret
  3. Add `DEPLOY_HOST` = `185.73.113.173` (or your server IP/hostname)
  4. Add `DEPLOY_USER` = `gold` (or your SSH username)
  5. Add `DEPLOY_PORT` = `2233` (or your SSH port, omit if using default 22)
  6. Add `DEPLOY_SSH_KEY` = paste your entire private key (including BEGIN/END lines)
  7. Add `DEPLOY_PATH` = `/home/gold/my-arbitrage-bot` (your server deployment directory)
  8. Ensure `.env.example` exists in the repository root (it's already included)
  9. Push to `develop` branch and watch the Actions tab for deployment status

### 7.6 Remote Restart Shortcut
- When you only need to restart the running container without shipping new code, run:
  ```
  pwsh -ExecutionPolicy Bypass -File deployment/restart.ps1 `
    -targetHost "rbot-server" `
    -User "gold" `
    -RemotePath "/home/gold/my-arbitrage-bot"
  ```
- Same parameter rule: include them inline if they are not coming from your shell profile. The script issues `docker compose restart arbitrage-bot` over SSH, which performs a graceful stop/start cycle and reloads the Python processes immediately.

### 7.7 Operational Observability
- Follow container logs with `ssh $user@$host "cd $TALATG_DEPLOY_PATH/deployment && docker compose logs -f arbitrage-bot"` to monitor trades, engine events, and errors.
- Inspect Redis health with `docker compose logs redis` or `docker compose exec redis redis-cli ping` if troubleshooting Pub/Sub traffic.
- For local smoke tests, you can run `docker compose -f deployment/docker-compose.yml up --build` directly on Windows (requires Docker Desktop) before promoting to the Linux server.

### 7.8 Failure Recovery Guarantees
- `depends_on` waits for the Redis health check to succeed before bringing up the bot container, preventing boot races at startup.
- `restart: unless-stopped` ensures both containers restart automatically after crashes or host reboots. To disable auto-restart temporarily, run `docker compose stop arbitrage-bot` instead of `down`.
- If you ever need to redeploy only the Python image (for example after editing dependencies), rerun `deploy.ps1`; Compose rebuilds the image layer cache and rolls forward with zero manual container management.


--------------------------
## Domain Context

### **Structure of the Telegram Trading Group**

In this Telegram group, trades are conducted by individuals under the supervision of the "Trading Supervisor".

***

### **Roles**

*   **Traders:** Human users with Telegram accounts who place and execute trades.
*   **Trading Supervisor:** A system responsible for confirming, recording, modifying, and matching trades.

***

### **Trader Operations and Messages**

#### **1. Placing a Buy Order**

*   **Message Format:** `[تعداد] + خ + [یک تا سه رقم آخر مظنه]`
*   **Description:** Numbers can be in Persian or English, and spacing can vary.
*   **Examples:**
    *   `1 خ 20`
    *   `4 خ 303`
    *   `۱ خ ۲۴`
    *   `۱خ۲۴`
    *   `۱خ35`

#### **2. Placing a Sell Order**

*   **Message Format:** `[تعداد] + ف + [یک تا سه رقم آخر مظنه]`
*   **Description:** Numbers can be in Persian or English, and spacing can vary.
*   **Examples:**
    *   `1 ف 20`
    *   `4 ف 303`
    *   `۱ ف ۲۴`
    *   `۱ف۲۴`
    *   `۱ف35`

#### **3. Canceling an Order (Sending "ن")**

*   **A) Canceling a specific order (by replying):**
    *   **Action:** The user replies with "ن" to their own order confirmation message which was posted by the Trading Supervisor.
    *   **Result:** The Trading Supervisor deletes that order message, and the order is canceled.
    *   **Example:**
        *   Trading Supervisor's message: `🔴 رضا 3 ف 45545`
        *   The user replies to this message with: `ن`
        *   Result: The order `🔴 رضا 3 ف 45545` is deleted.

*   **B) Canceling all orders (without replying):**
    *   **Action:** The user sends "ن" in the group without replying to a specific message.
    *   **Result:** All of the user's registered orders (both buy and sell) are removed from the group.
    *   **Example:**
        *   User's orders in the group:
            *   `🔴 رضا 3 ف 45545`
            *   `🔴 رضا 1 ف 45545`
            *   `🔵 رضا 1 خ 45550`
        *   The user sends: `ن`
        *   Result: All three orders above are canceled and deleted.

#### **4. Executing a Trade (Replying with "ب" or a number)**

*   **A) Accepting the entire order volume (by replying with "ب"):**
    *   **Action:** A trader replies with "ب" to another user's confirmed order message.
    *   **Result:** The trade is executed for the entire remaining volume of the order, and the Trading Supervisor issues a trade confirmation message.
    *   **Example 1 (Buying from a sell order):**
        *   Order message: `🔴 رضا 3 ف 45545`
        *   Another user replies: `ب`
        *   Trading Supervisor's message:
            ```
            🔵 خریدار :  [ اسم مستعار اون معامله گر ]
            🔴 فروشنده : محمد رضا
            ✅ تعداد: 3 قیمت:45,545,000 ✅
            ⏱️ ساعت: 21:43:35 1404/08/17
            🔖 شماره حواله: 101786
            ```
    *   **Example 2 (Selling to a buy order):**
        *   Order message: `🔵 بهار 3 خ 45520`
        *   Another user replies: `ب`
        *   Trading Supervisor's message:
            ```
            🔵 خریدار : بهار
            🔴 فروشنده : [ اسم مستعار اون معامله گر ]
            ✅ تعداد: 3 قیمت:45,520,000 ✅
            ⏱️ ساعت: 21:48:35 1404/08/17
            🔖 شماره حواله: 101784
            ```

*   **B) Accepting a partial volume of the order (by replying with a number):**
    *   **Action:** The trader replies with a number (Persian or English) corresponding to their desired volume on the order message.
    *   **Result:** The trade is executed for the specified quantity. The Trading Supervisor issues a trade confirmation and updates the original order message with the remaining volume.
    *   **Example:**
        *   Order message: `🔴 رضا 3 ف 45545`
        *   Another user replies: `1`
        *   Trading Supervisor's message for the trade confirmation:
            ```
            🔵 خریدار : [ معامله گری که عدد 1 را ریپلای کرده است ]
            🔴 فروشنده : رضا
            ✅ تعداد: 1 قیمت:45,520,000 ✅
            ⏱️ ساعت: 21:48:35 1404/08/17
            🔖 شماره حواله: 101784
            ```
        *   Modification of the original order message by the Trading Supervisor: `🔴 رضا 3 ف 45545 (مانده: 2 )`

***

### **Trading Supervisor Operations and Messages**

#### **1. Confirming and Formatting Orders**

*   **Action:** The Trading Supervisor deletes the user's raw message and posts it in a standard format, including the user's alias.
*   **Buy Order Confirmation:**
    *   User's message: `1خ20`
    *   Trading Supervisor's message: `🔵 بهار 1 خ 45520`
*   **Sell Order Confirmation:**
    *   User's message: `1ف50`
    *   Trading Supervisor's message: `🔴 لیلاج 1 ف 45550`

#### **2. Matching Two Trades**

*   **Action:** If a buy order and a sell order are placed with the same price and quantity, the Trading Supervisor automatically registers the trade.
*   **Result:** The Trading Supervisor (possibly) deletes the initial buy and sell order messages, leaving the trade confirmation message in the group.
*   **Example:**
    *   User 1: `1خ20`
    *   User 2: `1ف20`
    *   Trading Supervisor's message:
        ```
        🔵 خریدار : افتابی
        🔴 فروشنده : پیک
        ✅ تعداد: 1 قیمت:45,520,000 ✅
        ⏱️ ساعت: 21:48:35 1404/08/17
        🔖 شماره حواله: 101784
        ```

#### **3. Announcing the Market Price (Mazaneh)**

*   **Action:** The Trading Supervisor periodically announces the market price in the group.
*   **Message Format:** `🟡 مظنه:  [عدد متغیر] 🟡`
*   **Example:** `🟡 مظنه:  45540 🟡`

#### **4. Handling a User's Margin Call**

*   **Action:** If a user gets a margin call, all of their assets are automatically advertised as an order in the group.
*   **Examples:**
    *   `آگهی خودکار`
        `🔴 پروین 1 ف 45475`
    *   `آگهی خودکار`
        `🔵 پروین 6 خ 45475`



      ## TREE Telegram Trading Group
│
├── Roles
│   ├── Traders (Human users)
│   └── Trading Supervisor (Bot/System)
│
├── Trader Operations & Messages
│   │
│   ├── Buy Order
│   │   ├── Format: [qty] + خ + [1–3 digits]
│   │   └── Examples: (1 خ 20), (۱خ۲۴), ...
│   │
│   ├── Sell Order
│   │   ├── Format: [qty] + ف + [1–3 digits]
│   │   └── Examples: (1 ف 20), (۱ف۲۴), ...
│   │
│   ├── Cancel Orders ("ن")
│   │   │
│   │   ├── Reply "ن" → cancels that specific order
│   │   │   └── Example: reply “ن” → delete `🔴 رضا 3 ف 45545`
│   │   │
│   │   └── Standalone "ن" → cancels all user orders
│   │       └── Example: deletes:
│   │           ├─ 🔴 رضا 3 ف 45545
│   │           ├─ 🔴 رضا 1 ف 45545
│   │           └─ 🔵 رضا 1 خ 45550
│   │
│   ├── Execute Trades (Replying)
│   │   │
│   │   ├── Reply with "ب" → full match
│   │   │   ├── Example: reply "ب" on sell order
│   │   │   └── Example: reply "ب" on buy order
│   │   │
│   │   └── Reply with number → partial match
│   │       ├── Executes qty
│   │       └── Remaining qty updated → "(مانده: X)"
│   │
│   └── Notes
│       ├── Digits may be Persian/English
│       └── Spacing is flexible
│
├── Trading Supervisor Operations
│   │
│   ├── Order Confirmation
│   │   ├── Reformats buy orders → `🔵 [alias] qty خ price`
│   │   └── Reformats sell orders → `🔴 [alias] qty ف price`
│   │
│   ├── Auto-Matching
│   │   ├── If identical buy & sell appear → match
│   │   ├── Sends trade confirmation
│   │   └── May remove original orders
│   │
│   ├── Market Price Announcement
│   │   └── Format: `🟡 مظنه: <price> 🟡`
│   │
│   └── Margin Call Handling
│       ├── Auto announcement message
│       └── Format:
│           ├── 🔴 user qty ف price
│           └── 🔵 user qty خ price
│
└── Output Message Types
    ├── Order confirm
    ├── Trade execution
    ├── Order cancellation
    ├── Market price
    └── Margin call auto-ads



## **Arbitrage Bot Logic Document -(Distributed Architecture)**

### **Section 0: Overall Architecture and Technologies**

The system utilizes a distributed architecture with a centralized brain to bypass Telegram's rate limits and enhance stability.

*   **System Components:**
    1.  **Bot A (Source Group Agent):** A Telegram Userbot with a dedicated identity, active only in the **source group**. Its sole responsibilities are to report events and execute commands.
    2.  **Bot B (Destination Group Agent):** Identical to Bot A but operates exclusively in the **destination group**.
    3.  **Arbitrage Engine (Central Brain):** A standalone process that is **not** connected to Telegram. All decision-making logic, state management, and risk management are centralized here.

*   **Technologies:**
    *   **Redis:** Used for real-time communication between components (via Pub/Sub) and for storing live data (the order book and cache).
    *   **SQLite3:** Used for persistent storage of bot settings and for archiving trade history. It is accessed exclusively by the **Arbitrage Engine**.

---

### **Section 1: Initialization, Configuration, and Synchronization**

#### **1.1. Startup Process**
1.  The **Arbitrage Engine** starts and loads its configuration (e.g., timing parameters, `MINIMUM_PROFIT_SPREAD`) from the **SQLite3** database.
2.  **Bot A and Bot B** start, connect to Telegram, and begin listening to their respective Redis channels.

#### **1.2. State Management and Synchronization**
*   **Real-Time Synchronization:**
    *   **Example:**
        1.  A user posts a message in the **destination group**: `۱ خ ۵۰`
        2.  The "Trading Supervisor" confirms it: `🔵 بهار 1 خ 45550` (with `MessageID: 456`).
        3.  **Bot B** observes this `NewMessage` event and publishes a JSON message to the `group_events` Redis channel:
           `{'group': 'destination', 'type': 'new_message', 'data': {'message_id': 456, 'quantity': 1, 'price': 45550, 'owner': 'بهار', 'text': '🔵 بهار 1 خ 45550'}}`
        4.  The **Arbitrage Engine** receives this message and updates its `OrderBook`.
*   **Periodic Reconciliation:** **Every 1 minute**, the engine instructs the bots to verify the status of orders in the `OrderBook` via a single batch request, correcting any discrepancies.
*   **Data Archiving:** A process within the **Arbitrage Engine**, running every 50 minutes, archives `MessageID`s from the Redis `ExecutedTradesCache` into the **SQLite3** database for permanent storage.

---

Of course. Here is the complete, clean text ready for you to copy and paste directly into your document. All English explanations have been removed, leaving only the Persian section titles and the pure English content as requested.

---

### **Section 2: Trading Strategies and Execution Lifecycles**

The Arbitrage Engine employs a dual-strategy approach to maximize profitability. It dynamically chooses between two modes of operation based on real-time market conditions: **Immediate Arbitrage** (risk-free, reactive) and **Predictive Market-Making** (higher risk, proactive).

**2.1. Lifecycle of a Successful Immediate Arbitrage Trade (Reactive Strategy)**

#### **2.1.1. Opportunity Identification**
1.  **Current state of the Engine's `OrderBook`:** `{'destination': {456: {'owner': 'بهار', 'quantity': 1, 'price': 45550, ...}}}`
2.  **New Event (Trigger):** A new order is confirmed in the **source group**: `🔴 پروین 1 ف 45520` (with `MessageID: 123`).
3.  **Bot A** reports this event to the engine.
4.  **Engine Analysis:**
    *   Buy price in destination: `45550` | Sell price in source: `45520`.
    *   Profit: `45550 - 45520 = 30`. Assuming `MINIMUM_PROFIT_SPREAD = 10`, the opportunity is confirmed.

#### **2.1.2. Command Issuance and Distributed Execution**
1.  The **Arbitrage Engine** publishes two commands with a shared `trade_id` (`xyz-123`) to the `execution_commands` channel:
    *   `{'target_bot': 'A', 'action': 'reply', 'message_id': 123, 'quantity': 1, 'trade_id': 'xyz-123'}` *(Command to buy from Parvin)*
    *   `{'target_bot': 'B', 'action': 'reply', 'message_id': 456, 'quantity': 1, 'trade_id': 'xyz-123'}` *(Command to sell to Bahar)*
2.  **Bot A** consumes the first command and replies `۱` to message `123` in the source group.
3.  **Bot B** consumes the second command and replies `ب` to message `456` in the destination group.

#### **2.1.3. Monitoring and Precise Confirmation**
1.  **Bot A** enters a **3-second** monitoring phase in the source group and observes the following confirmation message from the Trading Supervisor:
    `🔵 خریدار: A | 🔴 فروشنده: پروین | ✅ تعداد: 1 قیمت:45,520,000 ✅`
    *   **Bot A's Analysis:** All 4 conditions (role, counterparty, price, quantity) are met. This leg of the trade is **successful**.
2.  Simultaneously, **Bot B** monitors the destination group and sees the confirmation:
    `🔵 خریدار: بهار | 🔴 فروشنده: B | ✅ تعداد: 1 قیمت:45,550,000 ✅`
    *   **Bot B's Analysis:** All 4 conditions are met. This leg is also **successful**.

#### **2.1.4. Reporting and Cycle Completion**
1.  **Bot A** publishes a success report to the `execution_results` channel:
    `{'status': 'success', 'bot': 'A', 'trade_id': 'xyz-123', 'traded_quantity': 1, ...}`
2.  **Bot B** publishes its own success report:
    `{'status': 'success', 'bot': 'B', 'trade_id': 'xyz-123', 'traded_quantity': 1, ...}`
3.  The **Arbitrage Engine** receives both reports. Since both legs were successful, it considers the trade complete and returns to an idle state.

**2.2. Lifecycle of a Successful Predictive Market-Making Trade (Proactive Strategy)**

This strategy is initiated when a favorable order appears in the source group, but no immediate, profitable counter-order exists in the destination group. Instead of passing on the opportunity, the engine attempts to *create* the opportunity by placing a speculative order.

#### **2.2.1. Trigger and Predictive Analysis**

1.  **Trigger Event:** A new order is confirmed in the **source group**: `🔴 رضا 1 ف 45540` (with `MessageID: 123`). Bot A reports this to the engine.
2.  **Engine Analysis:**
    *   The engine searches the destination group's `OrderBook` for a matching buy order. It finds none that meet the `MINIMUM_PROFIT_SPREAD`.
    *   **Strategy Switch:** Instead of discarding the event, the engine switches to the Predictive Market-Making strategy. It assumes that if `45540` is a good selling price in the source group, a slightly lower price might attract a seller in the destination group.

#### **2.2.2. Speculative Order Placement**

1.  **Command Issuance:** The engine calculates a new price. For a source sell order at `P`, it might place a destination buy order at `P - PREDICTIVE_SPREAD`.
    *   Example: `45540 - 10 = 45530`.
2.  The **Arbitrage Engine** issues a **single command** to the `execution_commands` channel with a unique `trade_id` (`spec-abc-456`):
    *   `{'target_bot': 'B', 'action': 'post_new_order', 'payload': {'side': 'buy', 'price': 45530, 'quantity': 1}, 'trade_id': 'spec-abc-456'}`
3.  **State Management:** Simultaneously, the engine creates a temporary state record in Redis for this trade, marking it as `PENDING_DESTINATION_FILL` with a timeout (e.g., 30 seconds). This record links the original source order (`🔴 رضا 1 ف 45540`) to the new speculative order.
4.  **Distributed Execution:** **Bot B** consumes the command and posts a new message in the destination group: `۱ خ ۳۰`. The Trading Supervisor confirms it: `🔵 [Bot B's Alias] 1 خ 45530`.

#### **2.2.3. Monitoring for the Second Leg (The Fill)**

1.  **The Bait is Set:** The engine is now waiting for someone in the destination group to accept Bot B's buy order.
2.  **Fill Event:** Another user ("سارا") replies to Bot B's order. The Trading Supervisor confirms the trade: `🔵 خریدار: [Bot B's Alias] | 🔴 فروشنده: سارا | ✅ تعداد: 1 ...`
3.  **Reporting:** **Bot B** observes this confirmation, recognizes it as a fill for its own order, and sends a `success` report for `trade_id: spec-abc-456` to the engine.

#### **2.2.4. Completing the Trade and Cycle Conclusion**

1.  **Final Command:** The engine receives the success report from Bot B. It retrieves the pending trade state from Redis and gets the details of the original source order (`🔴 رضا 1 ف 45540`).
2.  It immediately issues a final command to **Bot A**:
    *   `{'target_bot': 'A', 'action': 'reply', 'message_id': 123, 'quantity': 1, 'trade_id': 'spec-abc-456'}`
3.  **Execution and Confirmation:** Bot A replies to Reza's message, buying the item at `45540`.
4.  **Final Result:** The bot successfully bought from Sara at `45530` and sold to Reza at `45540`, securing a profit of `10`. The engine clears the trade state from Redis.

---

### **Section 3: Risk Management and Failure Scenarios**

**3.1. Failure Scenario in Immediate Arbitrage**

*   **Scenario:** Assume Bot A successfully bought from Parvin, but before Bot B could sell to Bahar, Bahar's order was taken by someone else.
1.  **Result Reporting:**
    *   Bot A sends a `success` report.
    *   After 3 seconds, Bot B, having seen no confirmation, sends a `failure` report with the reason `timeout`.
2.  **Engine's State Assessment:** The engine sees that for `trade_id: xyz-123`, one leg succeeded and one failed. It now holds an open position of 1 unit that must be sold.
3.  **Exit Strategy Execution:**
    *   **Layer 2 (Break-Even):** The engine issues a command for **Bot B** to create a new order: `🔴 B 1 ف 45520`. Bot B posts this order in the destination group. The engine waits for **2 seconds**.
    *   **Layer 3 (Stop-Loss):** Assume the order is not filled. The best buy offer in the destination group is now `🔵 علی 5 خ 45510`. The engine commands Bot B to cancel the previous order and post a more aggressive one: `🔴 B 1 ف 45505`. The engine waits another **4 seconds**.
    *   **Layer 4 (Emergency Liquidation):** Still not filled. The engine issues a final `emergency_liquidate` command. Bot B cancels its order and immediately replies `ب` to the best available buy order (`🔵 علی 5 خ 45510`) to exit the position at any price.
    *   **Circuit Breaker:** After this emergency exit is confirmed, the engine halts all trading activities for **10 minutes**.

**3.2. Failure Scenario in Predictive Market-Making**

This strategy introduces a new risk: the speculative order may never be filled, and the original opportunity in the source group might disappear.

*   **Scenario:** The engine places a speculative buy order for Bot B at `45530` in the destination group, corresponding to a sell order at `45540` in the source group. The pending trade state is set with a 30-second timeout.
1.  **Two Failure Paths:**
    *   **Path A (Timeout):** 30 seconds pass and no one accepts Bot B's buy order. The timeout in Redis expires.
    *   **Path B (Source Order Taken):** After 15 seconds, another user in the **source group** buys the item from Reza at `45540`. Bot A reports this "order taken" event to the engine.
2.  **Engine's Reaction (Order Cancellation):**
    *   In either path, the engine immediately identifies the corresponding `trade_id`.
    *   It issues a **cancellation command** to **Bot B**: `{'target_bot': 'B', 'action': 'cancel_own_order', 'message_id': [ID of Bot B's order], 'trade_id': 'spec-abc-456'}`.
3.  **Execution:** Bot B replies with "ن" to its own message (`🔵 [Bot B's Alias] 1 خ 45530`), and the order is removed by the Trading Supervisor.
4.  **Conclusion:** The trade attempt is aborted with no profit or loss. The engine cleans up the state from Redis and returns to an idle state.

---

### **Section 4: Crisis Management - Rate Limit with an Open Position**

*   **Scenario:** Bot A successfully buys 1 unit. Bot B attempts to sell but encounters a `FloodWaitError` for 25 seconds.
1.  **Crisis Reporting:** Bot B immediately sends a high-priority report to the engine:
    `{'status': 'execution_failed_flood', 'bot': 'B', 'trade_id': 'xyz-123', 'wait_duration': 25}`
2.  **Engine's Reaction:**
    *   The engine places the trade `xyz-123` into a `PENDING_FLOOD_EXIT` state.
    *   It takes no further action and simply waits for the 25-second flood wait to expire. All new opportunities are ignored.
3.  **Delayed Exit Protocol Execution:**
    *   After 25 seconds, the engine immediately issues an `emergency_liquidate` command to Bot B.
    *   Bot B, now free from the rate limit, receives the command, finds the best available buyer at that moment, and liquidates the position at any price.

---

#### **Section 5: Final Table of Configurable Parameters**

*These values are loaded from the `config.db` (SQLite3) file by the Arbitrage Engine at startup.*

| Parameter Name                           | Recommended Value | Description                                                                                             |
| ---------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------- |
| **`CONFIRMATION_TIMEOUT_SECONDS`**         | **3 seconds**     | The maximum time to wait for a trade confirmation from the Trading Supervisor.                          |
| **`RECONCILIATION_INTERVAL_MINUTES`**      | **1 minute**      | The time interval between periodic state synchronization cycles.                                        |
| **`EXIT_STRATEGY_TIMEOUT_SECONDS`**        | **2 seconds**     | The waiting period for the Layer 2 "Break-Even" exit strategy.                                          |
| **`EMERGENCY_TIMEOUT_SECONDS`**            | **4 seconds**     | The waiting period for the Layer 3 "Stop-Loss" exit strategy.                                           |
| **`CIRCUIT_BREAKER_DURATION_MINUTES`**     | **10 minutes**    | The duration the bot halts all activities after an emergency liquidation.                               |
| **`EXECUTED_CACHE_EXPIRATION_HOURS`**      | **1 hour**        | The time an executed trade's `MessageID` remains in the Redis cache to prevent reprocessing.            |
| **`PREDICTIVE_SPREAD`**                    | **10**            | The price difference the engine uses to place a speculative order in the destination group.             |
| **`SPECULATIVE_TRADE_TIMEOUT_SECONDS`**    | **60 seconds**    | The maximum time the engine will wait for a speculative order to be filled before cancelling it.        |
| **`SOURCE_ORDER_EXPIRY_SECONDS`**          | **60 seconds**    | Time after which an unfilled source confirmation expires and mirrored destination exposure is cancelled. |

---

### **Section 6: Management Panel**

To enable full control and dynamic configuration of the arbitrage system without direct code or database access, a dedicated Telegram Admin Bot panel will be implemented. This bot operates in a private management group, accessible only to approved admins.

**6.1. Panel Architecture**

*   **Admin Bot:** A standard Telegram bot (created via BotFather) serving as the user interface.
*   **Management Group:** A private Telegram group containing only the admin(s) and the Admin Bot.
*   **Engine Communication:** The Admin Bot communicates with the Arbitrage Engine via dedicated 
sending commands and receiving status updates. It is not directly coupled to the engine logic.

**6.2. Core Features & Capabilities**

The management panel, via inline keyboard buttons, provides the following capabilities:

#### **6.2.1. Dynamic Configuration**

Admins can adjust engine parameters live, without restarting the system. All parameters listed in Section 5 are configurable:

| Parameter Name                   | Example Values         | Description |
|----------------------------------|-----------------------|-------------|
| CONFIRMATION_TIMEOUT_SECONDS     | 1s, 3s, 5s            | Trade confirmation wait time |
| EXIT_STRATEGY_TIMEOUT_SECONDS    | 2s, 5s, 10s           | Break-even (Layer 2) wait |
| EMERGENCY_TIMEOUT_SECONDS        | 4s, 8s, 15s           | Stop-loss (Layer 3) wait |
| STOP_LOSS_PRICE_OFFSET           | 5, 10, 20             | Price offset before emergency exit |
| CIRCUIT_BREAKER_DURATION_MINUTES | 5, 10, 30             | Post-emergency halt duration |
| AUTO_N_DELAY_SECONDS             | 0, 3, 10, 30          | Delay before sending `ن` acknowledgements |
| PREDICTIVE_PRICE_DELTA           | 5, 10, 15             | Speculative spread delta |
| PREDICTIVE_SUFFIX_DIGITS         | 3, 4, 5               | Digits appended to speculative orders |
| SPECULATIVE_TRADE_TIMEOUT_SECONDS| 30, 60, 120           | Destination fill timeout |
| SOURCE_ORDER_EXPIRY_SECONDS      | 30, 60, 90            | Lifetime of source confirmations |

#### **6.2.2. Exit Strategy Layer Control**

Admins can enable/disable each exit strategy layer (e.g., Layer 2: Break-Even, Layer 3: Stop-Loss) independently. If only Layer 4 (Emergency Liquidation) is enabled, failed trades will skip directly to emergency exit. Layer toggling is done via inline buttons.

#### **6.2.3. Real-Time Statistics & Reporting**

The bot periodically (e.g., hourly) or on-demand posts performance reports in the management group:

*   **Source Group:** Total buys/sells
*   **Destination Group:** Total buys/sells
*   **Profit/Loss (PNL):** Estimated total, successful trades, emergency exits

#### **6.2.4. Operational Status Control**

*   **Panic Button:** Instantly halts all trading activity. No new opportunities are processed.
*   **Pause / Resume:** Toggle monitor-only mode so orders can drain safely.
*   **Stop / Start Engine:** Issue a full shutdown or restart without SSH access.

#### **6.2.5. Alerts & Notifications**

*   **Service Outage Alerts:** If any Docker container (bot_agent_A, bot_agent_B, engine) goes down, an immediate alert is posted. This is implemented via a health check service.
*   **Emergency Exit Reports:** Every time a trade reaches Layer 4 (emergency liquidation), details are posted instantly.
*   **Critical Error Reports:** Any unexpected engine or bot error is reported for admin review.
*   **Deployment Broadcasts:** On every CI deploy the admin bot posts status (started/success/failed), commit hash, author, and summary.

#### **6.2.6. Monitor-Only Mode**

A dedicated button places the engine in "monitor-only" mode: opportunities are detected and reported, but no trades are executed. This is ideal for strategy testing or market observation without financial risk.

#### **6.2.7. Open Trades List**

Admins can request a list of all trades currently in the `PENDING_SPECULATIVE_TRADE` state, showing which trades are still at risk.

#### **6.2.8. Safe Shutdown Logic**

When an admin requests to disable the engine, the system first checks for any open trades or ongoing risk (e.g., pending speculative trades). If such trades exist, the shutdown command is held, and the admin is notified: "Shutdown pending: currently processing [operation]. Will shut down automatically when complete." Once all trades are resolved, the engine shuts down and posts a confirmation in the admin group: "Engine has been shut down."

---

## **Important Constraints**

This section outlines the technical, operational, and external dependency constraints upon which the correct and successful operation of the bot depends.

### **Technical Constraints**

1.  **Critical Reliance on Redis for Real-Time Communication:**
    *   The entire distributed architecture is built upon instantaneous communication between the Arbitrage Engine and Bots A and B via Redis Pub/Sub. Any disruption or latency in the Redis service will cause a complete failure of the decision-making and trade execution system.

2.  **Requirement for Telegram User Accounts (Userbots):**
    *   The bots operate using the Telethon library with real phone numbers, not standard bot tokens. This constraint requires managing login processes, two-factor authentication (2FA), and stricter adherence to Telegram's terms of service to prevent account suspension.

3.  **Sensitivity to Network Performance and Latency:**
    *   Successful arbitrage depends on sub-second decision-making and execution. Any network latency between the bot's server, the Redis server, and Telegram's servers can result in missed trading opportunities.

### **Operational Constraints**

1.  **Permanent State Integrity and Synchronization:**
    *   The bot's operational integrity is entirely dependent on the accuracy of its internal `OrderBook`. If the synchronization process (both real-time and periodic) fails, the bot will make decisions based on incorrect data, which could lead to loss-making trades.

2.  **Full Reliance on Automation (No Manual Intervention):**
    *   The risk management and emergency exit strategies are designed to be fully automated. Any attempt at manual intervention during a crisis (e.g., a human canceling an order) can disrupt the bot's automated logic and lead to unpredictable outcomes or greater losses.

### **External Dependencies**

1.  **Strict Dependency on the "Trading Supervisor's" Message Formats:**
    *   This is the **single most critical and fragile point of failure** in the system. The bot's logic for identifying orders, confirming trades, and understanding the market state relies entirely on parsing the text messages posted by the "Trading Supervisor." **Any change, however minor** (such as a modified emoji, an extra space, or rephrasing), in the supervisor's message templates will break the bot's parser and render the entire system inoperable until the code is updated.

2.  **Telegram Platform Stability and Policies:**
    *   The bot's functionality is wholly dependent on the stability of the Telegram API. Any downtime or performance degradation of Telegram's services will directly impact the bot. Furthermore, potential changes to Telegram's anti-spam algorithms or rate-limiting policies may require a redesign of the bot's architecture or strategies.

3.  **Uninterrupted Access to Target Groups:**
    *   The user accounts for Bot A and Bot B must remain permanent members of both the source and destination groups. If either account is kicked or banned from a group, the bot will be blinded on that side, and all arbitrage operations will cease.


## **External Dependencies**

