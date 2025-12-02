"""Configuration management for API keys and settings.

Loads configuration from environment variables or .env file.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class APIConfig:
    """API configuration for all data providers."""

    # CoinGecko
    coingecko_api_key: Optional[str] = None

    # CryptoRank
    cryptorank_api_key: Optional[str] = None

    # Flipside Crypto
    flipside_api_key: Optional[str] = None

    # DropsTab
    dropstab_api_key: Optional[str] = None

    # CoinMarketCap
    coinmarketcap_api_key: Optional[str] = None

    # Messari
    messari_api_key: Optional[str] = None

    # Tokenomist
    tokenomist_api_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Load configuration from environment variables."""
        return cls(
            coingecko_api_key=os.getenv("COINGECKO_API_KEY"),
            cryptorank_api_key=os.getenv("CRYPTORANK_API_KEY"),
            flipside_api_key=os.getenv("FLIPSIDE_API_KEY"),
            dropstab_api_key=os.getenv("DROPSTAB_API_KEY"),
            coinmarketcap_api_key=os.getenv("COINMARKETCAP_API_KEY"),
            messari_api_key=os.getenv("MESSARI_API_KEY"),
            tokenomist_api_key=os.getenv("TOKENOMIST_API_KEY"),
        )

    @classmethod
    def load(cls, env_file: Optional[Path] = None) -> "APIConfig":
        """
        Load configuration from .env file and environment variables.

        Args:
            env_file: Optional path to .env file. If not provided,
                      looks for .env in the project root.

        Returns:
            APIConfig instance with loaded values
        """
        # Try to load .env file if python-dotenv is available
        try:
            from dotenv import load_dotenv

            if env_file:
                load_dotenv(env_file)
            else:
                # Look for .env in project root
                project_root = Path(__file__).parent.parent.parent
                env_path = project_root / ".env"
                if env_path.exists():
                    load_dotenv(env_path)
        except ImportError:
            # python-dotenv not installed, just use env vars
            pass

        return cls.from_env()

    def has_flipside(self) -> bool:
        """Check if Flipside API key is configured."""
        return bool(self.flipside_api_key)

    def has_cryptorank(self) -> bool:
        """Check if CryptoRank API key is configured."""
        return bool(self.cryptorank_api_key)

    def has_dropstab(self) -> bool:
        """Check if DropsTab API key is configured."""
        return bool(self.dropstab_api_key)

    def has_coingecko(self) -> bool:
        """Check if CoinGecko API key is configured (optional)."""
        return bool(self.coingecko_api_key)

    def get_available_sources(self) -> list[str]:
        """Get list of configured data sources."""
        sources = ["ccxt"]  # Always available (no API key needed)

        # CoinGecko works without API key (rate limited)
        sources.append("coingecko")

        if self.flipside_api_key:
            sources.append("flipside")
        if self.cryptorank_api_key:
            sources.append("cryptorank")
        if self.dropstab_api_key:
            sources.append("dropstab")
        if self.coinmarketcap_api_key:
            sources.append("coinmarketcap")
        if self.messari_api_key:
            sources.append("messari")
        if self.tokenomist_api_key:
            sources.append("tokenomist")

        return sources


# Global config instance (lazy loaded)
_config: Optional[APIConfig] = None


def get_config() -> APIConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = APIConfig.load()
    return _config


def reload_config(env_file: Optional[Path] = None) -> APIConfig:
    """Reload configuration from environment."""
    global _config
    _config = APIConfig.load(env_file)
    return _config
