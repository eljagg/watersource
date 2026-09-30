"""App configuration for accounts."""
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Registers the accounts app and its signal handlers."""
    name = "apps.accounts"
    verbose_name = "Accounts and roles"
