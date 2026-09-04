"""Greedy SQL generation with execution-driven self-repair: the generated query is executed against the database and any execution error is fed back into the prompt for up to three corrective regeneration attempts."""
# MECHANISM: repair

from