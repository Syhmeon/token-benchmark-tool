"""Manual allocation provider for analyst overrides.

Allows analysts to provide allocation data via YAML/JSON files
when automated sources are incomplete or incorrect.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ...core.models import RawAllocation, SourceReference, VestingTerms
from ...core.types import DataSource, VestingScheduleType
from ..base import BaseProvider

logger = logging.getLogger(__name__)


class ManualAllocationProvider(BaseProvider):
    """Loads allocation data from manual YAML/JSON files."""

    SOURCE = DataSource.MANUAL

    def __init__(self, data_directory: Path | str | None = None):
        """
        Initialize manual allocation provider.

        Args:
            data_directory: Directory containing manual allocation files.
                Files should be named {token_id}.yaml or {token_id}.json
        """
        super().__init__()
        self.data_directory = Path(data_directory) if data_directory else None

    def is_available(self) -> bool:
        """Check if data directory exists and is readable."""
        if self.data_directory is None:
            return False
        return self.data_directory.exists() and self.data_directory.is_dir()

    def _find_allocation_file(self, token_id: str) -> Path | None:
        """Find allocation file for a token."""
        if not self.data_directory:
            return None

        # Try different file names and extensions
        candidates = [
            f"{token_id}.yaml",
            f"{token_id}.yml",
            f"{token_id}.json",
            f"{token_id.lower()}.yaml",
            f"{token_id.lower()}.yml",
            f"{token_id.lower()}.json",
            f"{token_id.upper()}.yaml",
            f"{token_id.upper()}.yml",
            f"{token_id.upper()}.json",
        ]

        for filename in candidates:
            filepath = self.data_directory / filename
            if filepath.exists():
                return filepath

        return None

    def _load_file(self, filepath: Path) -> dict[str, Any]:
        """Load YAML or JSON file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                if filepath.suffix in (".yaml", ".yml"):
                    return yaml.safe_load(f) or {}
                else:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {filepath}: {e}")
            return {}

    def _parse_vesting(self, vesting_data: dict[str, Any] | str | None) -> VestingTerms | None:
        """Parse vesting information from manual data."""
        if not vesting_data:
            return None

        # If it's just a string description
        if isinstance(vesting_data, str):
            return VestingTerms(raw_description=vesting_data)

        # Parse structured vesting data
        schedule_raw = vesting_data.get("schedule_type", "")
        schedule_type = VestingScheduleType.UNKNOWN

        if schedule_raw:
            schedule_lower = str(schedule_raw).lower()
            if schedule_lower == "linear":
                schedule_type = VestingScheduleType.LINEAR
            elif schedule_lower == "cliff":
                schedule_type = VestingScheduleType.CLIFF
            elif schedule_lower == "step":
                schedule_type = VestingScheduleType.STEP
            elif schedule_lower == "custom":
                schedule_type = VestingScheduleType.CUSTOM

        # Parse dates
        start_date = None
        end_date = None
        if vesting_data.get("start_date"):
            try:
                start_date = datetime.fromisoformat(str(vesting_data["start_date"]))
            except ValueError:
                pass
        if vesting_data.get("end_date"):
            try:
                end_date = datetime.fromisoformat(str(vesting_data["end_date"]))
            except ValueError:
                pass

        return VestingTerms(
            tge_unlock_pct=vesting_data.get("tge_unlock_pct"),
            cliff_months=vesting_data.get("cliff_months"),
            vesting_months=vesting_data.get("vesting_months"),
            schedule_type=schedule_type,
            unlock_frequency=vesting_data.get("unlock_frequency"),
            start_date=start_date,
            end_date=end_date,
            raw_description=vesting_data.get("description"),
            notes=vesting_data.get("notes"),
        )

    def get_allocations(self, token_id: str) -> list[RawAllocation]:
        """
        Load manual allocations for a token.

        Args:
            token_id: Token identifier (CoinGecko ID or symbol)

        Returns:
            List of RawAllocation objects from manual file
        """
        filepath = self._find_allocation_file(token_id)

        if not filepath:
            logger.debug(f"No manual allocation file found for {token_id}")
            return []

        data = self._load_file(filepath)

        if not data:
            return []

        self._record_audit(
            action="load",
            endpoint=str(filepath),
            success=True,
            notes=f"Loaded manual allocations for {token_id}",
        )

        source_ref = SourceReference(
            source=DataSource.MANUAL,
            url=f"file://{filepath.absolute()}",
            endpoint=str(filepath),
        )

        allocations = []
        allocation_list = data.get("allocations", [])

        for item in allocation_list:
            vesting = self._parse_vesting(item.get("vesting"))

            allocation = RawAllocation(
                source=DataSource.MANUAL,
                label=item.get("label", "Unknown"),
                percentage=item.get("percentage"),
                amount=item.get("amount"),
                vesting=vesting,
                source_reference=source_ref,
            )
            allocations.append(allocation)

        logger.info(f"Loaded {len(allocations)} manual allocations for {token_id}")
        return allocations

    def load_from_dict(
        self,
        allocations_data: list[dict[str, Any]],
        notes: str | None = None,
    ) -> list[RawAllocation]:
        """
        Load allocations directly from a dictionary (for programmatic use).

        Args:
            allocations_data: List of allocation dictionaries
            notes: Optional notes about the data source

        Returns:
            List of RawAllocation objects

        Example:
            ```python
            provider = ManualAllocationProvider()
            allocations = provider.load_from_dict([
                {"label": "Team", "percentage": 15.0, "vesting": {"cliff_months": 12}},
                {"label": "Investors", "percentage": 20.0},
            ])
            ```
        """
        source_ref = SourceReference(
            source=DataSource.MANUAL,
            endpoint="programmatic",
        )

        if notes:
            self._record_audit(
                action="load",
                endpoint="programmatic",
                success=True,
                notes=notes,
            )

        allocations = []
        for item in allocations_data:
            vesting = self._parse_vesting(item.get("vesting"))

            allocation = RawAllocation(
                source=DataSource.MANUAL,
                label=item.get("label", "Unknown"),
                percentage=item.get("percentage"),
                amount=item.get("amount"),
                vesting=vesting,
                source_reference=source_ref,
            )
            allocations.append(allocation)

        return allocations
