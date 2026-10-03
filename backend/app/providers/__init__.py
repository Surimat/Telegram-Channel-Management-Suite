"""Telegram provider interfaces and implementations.

All Telegram access is behind these abstractions (decision D-001). Real
implementations wrap aiogram/Telethon; fake implementations let the whole
business logic be tested without a real account. Concrete implementations are
added in later phases; this package holds the shared contracts.
"""
