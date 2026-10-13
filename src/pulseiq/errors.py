"""Exception types. They map to different exit codes so failures are distinguishable."""


class PulseIQError(Exception):
    """Base class for expected pipeline failures."""


class ConfigError(PulseIQError):
    """A setting in the environment is missing or malformed."""


class StructuralError(PulseIQError):
    """The input is not shaped as expected: missing file, sheet or column."""
