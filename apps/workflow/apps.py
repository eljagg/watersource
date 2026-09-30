"""App configuration for the workflow engine."""
from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    """Registers the workflow app."""
    name = "apps.workflow"
    verbose_name = "Approval workflows"
