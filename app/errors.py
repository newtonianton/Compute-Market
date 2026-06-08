"""
Typed market errors.

Routers raise these instead of fiddling with HTTP status codes inline; a single
exception handler in main.py turns them into clean JSON responses. Add new ones
here as your rules grow (e.g. MarketHalted, OrderTooSmall).
"""


class MarketError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class NotFound(MarketError):
    status_code = 404


class NotWhitelisted(MarketError):
    status_code = 403


class InsufficientCapacity(MarketError):
    status_code = 409


class InsufficientFunds(MarketError):
    status_code = 409


class BadRequest(MarketError):
    status_code = 400
