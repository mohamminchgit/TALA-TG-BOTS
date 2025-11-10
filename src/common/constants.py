import re

ORDER_BUY_PATTERN = re.compile(r"🔵\s+(\S+)\s+([۰-۹0-9]+)\s+خ\s+([۰-۹0-9]+)")
ORDER_SELL_PATTERN = re.compile(r"🔴\s+(\S+)\s+([۰-۹0-9]+)\s+ف\s+([۰-۹0-9]+)")
MARKET_PRICE_PATTERN = re.compile(r"🟡\s*مظنه:\s*([۰-۹0-9]+)\s*🟡")
TRADE_CONFIRMATION_PATTERN = re.compile(
    r"🔵\s*خریدار\s*:\s*(?P<buyer>[^\n]+?)"
    r".*?🔴\s*فروشنده\s*:\s*(?P<seller>[^\n]+?)"
    r".*?تعداد\s*:?\s*(?P<quantity>[۰-۹0-9]+)"
    r".*?قیمت\s*:?\s*(?P<price>[۰-۹0-9,]+)"
    r"(?:.*?شماره\s*حواله\s*:?\s*(?P<reference>[۰-۹0-9]+))?",
    re.DOTALL,
)

PERSIAN_TO_ENGLISH = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
