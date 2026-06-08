"""
Shared configuration defaults.
Override any value by passing CLI arguments to backtrack.py or standard.py.
"""

REQUEST_DELAY: float = 1.0
REQUEST_TIMEOUT: int = 30
STANDARD_INTERVAL: int = 300  # 5 minutes
BACKTRACK_OUTPUT: str = "backtrack_output.json"
STANDARD_OUTPUT: str = "standard_output.json"
