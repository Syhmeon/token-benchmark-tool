"""Vesting schedule parser.

Parses free-text vesting descriptions into structured VestingTerms objects.
Handles common formats like:
- "10% TGE, 6 month cliff, 24 months linear"
- "20% at launch, then monthly over 12 months"
- "1 year cliff, 2 years linear vesting"
"""

import logging
import re
from typing import Any

from ..core.models import VestingTerms
from ..core.types import VestingScheduleType

logger = logging.getLogger(__name__)


# Common patterns for parsing vesting text
PATTERNS = {
    # TGE unlock: "10% TGE", "10% at TGE", "10% at launch", "10% initial"
    "tge_unlock": [
        r"(\d+(?:\.\d+)?)\s*%?\s*(?:at\s+)?(?:tge|launch|listing|initial|unlock)",
        r"(?:tge|launch|listing|initial)\s*(?:unlock)?\s*(?:of\s+)?(\d+(?:\.\d+)?)\s*%",
    ],
    # Cliff: "6 month cliff", "6-month cliff", "6m cliff", "cliff of 6 months"
    "cliff_months": [
        r"(\d+)\s*[-]?\s*(?:month|mo|m)\s*cliff",
        r"cliff\s*(?:of\s+)?(\d+)\s*(?:month|mo|m)",
        r"(\d+)\s*year\s*cliff",  # Will multiply by 12
    ],
    # Vesting duration: "24 months linear", "2 years vesting", "linear over 12 months"
    "vesting_months": [
        r"(?:over|for|linear)\s*(\d+)\s*(?:month|mo|m)",
        r"(\d+)\s*(?:month|mo|m)\s*(?:linear|vesting)",
        r"(\d+)\s*year[s]?\s*(?:linear|vesting)",  # Will multiply by 12
    ],
    # Schedule type
    "linear": r"linear|straight|continuous",
    "monthly": r"monthly|each\s*month",
    "quarterly": r"quarterly|every\s*(?:3|three)\s*month",
    "cliff_only": r"cliff\s*(?:release|unlock)|(?:release|unlock)\s*after\s*cliff",
}


class VestingParser:
    """Parses vesting descriptions into structured data."""

    def __init__(self):
        """Initialize the vesting parser."""
        self._compiled: dict[str, list[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns."""
        for key, patterns in PATTERNS.items():
            if isinstance(patterns, list):
                self._compiled[key] = [
                    re.compile(p, re.IGNORECASE) for p in patterns
                ]
            else:
                self._compiled[key] = [re.compile(patterns, re.IGNORECASE)]

    def _extract_number(
        self,
        text: str,
        pattern_key: str,
        multiply_years: bool = True,
    ) -> float | None:
        """
        Extract a number from text using patterns.

        Args:
            text: Text to search
            pattern_key: Key in PATTERNS dict
            multiply_years: If True, multiply year values by 12

        Returns:
            Extracted number or None
        """
        patterns = self._compiled.get(pattern_key, [])

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                value = float(match.group(1))

                # Check if this was a year pattern and convert
                if multiply_years and "year" in pattern.pattern:
                    value *= 12

                return value

        return None

    def _detect_schedule_type(self, text: str) -> VestingScheduleType:
        """Detect the vesting schedule type from text."""
        text_lower = text.lower()

        # Check for cliff-only release
        if any(p.search(text_lower) for p in self._compiled.get("cliff_only", [])):
            return VestingScheduleType.CLIFF

        # Check for linear
        if any(p.search(text_lower) for p in self._compiled.get("linear", [])):
            return VestingScheduleType.LINEAR

        # Check for step schedules
        if any(p.search(text_lower) for p in self._compiled.get("monthly", [])):
            return VestingScheduleType.STEP
        if any(p.search(text_lower) for p in self._compiled.get("quarterly", [])):
            return VestingScheduleType.STEP

        return VestingScheduleType.UNKNOWN

    def _detect_frequency(self, text: str) -> str | None:
        """Detect unlock frequency from text."""
        text_lower = text.lower()

        if any(p.search(text_lower) for p in self._compiled.get("monthly", [])):
            return "monthly"
        if any(p.search(text_lower) for p in self._compiled.get("quarterly", [])):
            return "quarterly"

        return None

    def parse(self, text: str | None) -> VestingTerms | None:
        """
        Parse a vesting description into structured terms.

        Args:
            text: Free-text vesting description

        Returns:
            VestingTerms or None if text is empty/unparseable
        """
        if not text:
            return None

        text = str(text).strip()

        if not text:
            return None

        # Extract components
        tge_unlock = self._extract_number(text, "tge_unlock", multiply_years=False)
        cliff_months = self._extract_number(text, "cliff_months")
        vesting_months = self._extract_number(text, "vesting_months")
        schedule_type = self._detect_schedule_type(text)
        frequency = self._detect_frequency(text)

        # Convert to integers where appropriate
        cliff_int = int(cliff_months) if cliff_months else None
        vesting_int = int(vesting_months) if vesting_months else None

        # Only create VestingTerms if we extracted something
        if any([tge_unlock, cliff_int, vesting_int, schedule_type != VestingScheduleType.UNKNOWN]):
            return VestingTerms(
                tge_unlock_pct=tge_unlock,
                cliff_months=cliff_int,
                vesting_months=vesting_int,
                schedule_type=schedule_type,
                unlock_frequency=frequency,
                raw_description=text,
            )

        # Return with just the raw description
        return VestingTerms(raw_description=text)

    def parse_dict(self, data: dict[str, Any] | None) -> VestingTerms | None:
        """
        Parse vesting from a dictionary (common in API responses).

        Handles various field naming conventions.

        Args:
            data: Dictionary with vesting fields

        Returns:
            VestingTerms or None
        """
        if not data:
            return None

        # Try to extract fields with various naming conventions
        tge_unlock = (
            data.get("tge_unlock_pct")
            or data.get("tgeUnlock")
            or data.get("initial_unlock")
            or data.get("initialUnlock")
            or data.get("tge")
        )

        cliff = (
            data.get("cliff_months")
            or data.get("cliffMonths")
            or data.get("cliff")
        )

        vesting = (
            data.get("vesting_months")
            or data.get("vestingMonths")
            or data.get("duration")
            or data.get("durationMonths")
        )

        schedule = (
            data.get("schedule_type")
            or data.get("scheduleType")
            or data.get("type")
            or data.get("schedule")
        )

        frequency = (
            data.get("unlock_frequency")
            or data.get("unlockFrequency")
            or data.get("frequency")
        )

        description = (
            data.get("raw_description")
            or data.get("description")
            or data.get("notes")
            or data.get("text")
        )

        # Parse schedule type
        schedule_type = VestingScheduleType.UNKNOWN
        if schedule:
            schedule_str = str(schedule).lower()
            if schedule_str == "linear":
                schedule_type = VestingScheduleType.LINEAR
            elif schedule_str in ("cliff", "cliff_only"):
                schedule_type = VestingScheduleType.CLIFF
            elif schedule_str in ("step", "periodic"):
                schedule_type = VestingScheduleType.STEP
            elif schedule_str == "custom":
                schedule_type = VestingScheduleType.CUSTOM

        # Convert to appropriate types
        tge_float = float(tge_unlock) if tge_unlock is not None else None
        cliff_int = int(cliff) if cliff is not None else None
        vesting_int = int(vesting) if vesting is not None else None

        if any([tge_float, cliff_int, vesting_int, description]):
            return VestingTerms(
                tge_unlock_pct=tge_float,
                cliff_months=cliff_int,
                vesting_months=vesting_int,
                schedule_type=schedule_type,
                unlock_frequency=frequency,
                raw_description=description,
            )

        return None

    def format_summary(self, terms: VestingTerms | None) -> str:
        """
        Format vesting terms as a human-readable summary.

        Args:
            terms: VestingTerms to format

        Returns:
            Formatted string summary
        """
        if not terms:
            return "No vesting info"

        parts = []

        if terms.tge_unlock_pct is not None:
            parts.append(f"{terms.tge_unlock_pct:.0f}% TGE")

        if terms.cliff_months:
            parts.append(f"{terms.cliff_months}mo cliff")

        if terms.vesting_months:
            schedule_str = ""
            if terms.schedule_type == VestingScheduleType.LINEAR:
                schedule_str = "linear"
            elif terms.schedule_type == VestingScheduleType.STEP:
                freq = terms.unlock_frequency or "periodic"
                schedule_str = freq

            if schedule_str:
                parts.append(f"{terms.vesting_months}mo {schedule_str}")
            else:
                parts.append(f"{terms.vesting_months}mo vesting")

        if parts:
            return ", ".join(parts)

        if terms.raw_description:
            # Truncate if too long
            desc = terms.raw_description
            if len(desc) > 50:
                desc = desc[:47] + "..."
            return desc

        return "Vesting details available"
