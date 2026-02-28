"""Rate limiter singleton — import from here to avoid circular deps."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
