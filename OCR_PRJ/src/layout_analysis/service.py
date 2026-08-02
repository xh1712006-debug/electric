"""Backward-compatible imports for the page-3+ production service."""

from .page3_plus.service import DocumentLayoutAnalysisService, Page3PlusLayoutAnalysisService, PageLayoutResult

__all__ = ["DocumentLayoutAnalysisService", "Page3PlusLayoutAnalysisService", "PageLayoutResult"]
