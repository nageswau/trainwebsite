"""nehn-009 (DEC-SCOPE-303): the report framework. Importing the package registers every report module."""

from app.services.reports import placement, training  # noqa: F401  (registers the training reports; nehn-016 the placement reports)
