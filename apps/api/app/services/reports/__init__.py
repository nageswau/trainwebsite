"""nehn-009 (DEC-SCOPE-303): the report framework. Importing the package registers every report module."""

from app.services.reports import training  # noqa: F401  (registers the training reports)
