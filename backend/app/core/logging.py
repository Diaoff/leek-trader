import logging
from logging.handlers import RotatingFileHandler

from app.core.config import settings

LOGS_DIR = settings.resolved_log_dir

os = __import__("os")
os.makedirs(LOGS_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.is_development else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        # Console handler
        logging.StreamHandler(),
        # File handler with rotation
        RotatingFileHandler(
            os.path.join(LOGS_DIR, "app.log"),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
    ]
)

# Create logger for the application
logger = logging.getLogger("leek_trader")

# Create loggers for specific modules
auth_logger = logging.getLogger("leek_trader.auth")
trading_logger = logging.getLogger("leek_trader.trading")
market_logger = logging.getLogger("leek_trader.market")
portfolio_logger = logging.getLogger("leek_trader.portfolio")
risk_logger = logging.getLogger("leek_trader.risk")
audit_logger = logging.getLogger("leek_trader.audit")

# Add file handlers for specific modules
trading_handler = RotatingFileHandler(
    os.path.join(LOGS_DIR, "trading.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3
)
trading_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
trading_logger.addHandler(trading_handler)

market_handler = RotatingFileHandler(
    os.path.join(LOGS_DIR, "market.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3
)
market_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
market_logger.addHandler(market_handler)

portfolio_handler = RotatingFileHandler(
    os.path.join(LOGS_DIR, "portfolio.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3
)
portfolio_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
portfolio_logger.addHandler(portfolio_handler)

audit_handler = RotatingFileHandler(
    os.path.join(LOGS_DIR, "audit.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
)
audit_handler.setFormatter(logging.Formatter("%(message)s"))
audit_logger.addHandler(audit_handler)
audit_logger.propagate = False
