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

    # CoinGecko (optional - public API works without key)
    coingecko_api_key: Optional[str] = None

    # CryptoRank (fundraising, investors) - Sandbox plan limited
    cryptorank_api_key: Optional[str] = None

    # CoinMarketCap (price backup, holders, DEX overview)
    coinmarketcap_api_key: Optional[str] = None

    # Messari (backup - fundraising)
    messari_api_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Load configuration from environment variables."""
        return cls(
            coingecko_api_key=os.getenv("COINGECKO_API_KEY"),
            cryptorank_api_key=os.getenv("CRYPTORANK_API_KEY"),
            coinmarketcap_api_key=os.getenv("COINMARKETCAP_API_KEY"),
            messari_api_key=os.getenv("MESSARI_API_KEY"),
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

    def has_cryptorank(self) -> bool:
        """Check if CryptoRank API key is configured."""
        return bool(self.cryptorank_api_key)

    def has_coinmarketcap(self) -> bool:
        """Check if CoinMarketCap API key is configured."""
        return bool(self.coinmarketcap_api_key)

    def has_messari(self) -> bool:
        """Check if Messari API key is configured."""
        return bool(self.messari_api_key)

    def has_coingecko(self) -> bool:
        """Check if CoinGecko API key is configured (optional)."""
        return bool(self.coingecko_api_key)

    def get_available_sources(self) -> list[str]:
        """Get list of configured data sources."""
        sources = ["ccxt"]  # Always available (no API key needed)

        # CoinGecko works without API key (rate limited)
        sources.append("coingecko")

        if self.cryptorank_api_key:
            sources.append("cryptorank")
        if self.coinmarketcap_api_key:
            sources.append("coinmarketcap")
        if self.messari_api_key:
            sources.append("messari")

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
