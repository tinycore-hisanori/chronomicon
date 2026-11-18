"""Pytest configuration: Hypothesis profiles.

Select a profile with the HYPOTHESIS_PROFILE environment variable (default: dev).
  dev: 25 examples per property, keeps the whole suite under 60 seconds.
  ci:  200 examples per property.
"""

from __future__ import annotations

import os

from hypothesis import settings

settings.register_profile("dev", max_examples=25, deadline=None)
settings.register_profile("ci", max_examples=200, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
