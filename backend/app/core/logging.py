import logging
import os
from logging.handlers import RotatingFileHandler

from app.core.config import settings

# Create logs directory if it doesn't exist
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
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
