"""Error type shared by all converter stages."""


class ConversionError(Exception):
    """Aborts the conversion. The message is written to stderr by converter.py."""
