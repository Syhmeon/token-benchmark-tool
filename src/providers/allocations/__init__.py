"""Allocation data providers."""

from .cryptorank_alloc import CryptoRankAllocationProvider
from .manual_alloc import ManualAllocationProvider

__all__ = ["CryptoRankAllocationProvider", "ManualAllocationProvider"]
