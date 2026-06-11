"""Domain errors. main.py maps MarketError -> JSON error response."""


class MarketError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class BadRequest(MarketError):
    status_code = 400


class NotFound(MarketError):
    status_code = 404


class Forbidden(MarketError):
    status_code = 403


class InsufficientFunds(MarketError):
    status_code = 402


class InsufficientCapacity(MarketError):
    status_code = 409


class InsufficientBond(MarketError):
    status_code = 409
