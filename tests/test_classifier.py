"""
Tests for File Classifier.
"""

from pathlib import Path
from svant.core.classifier import FileClassifier, FileCategory


def test_classifier_categories():
    assert FileClassifier.classify("main.py").category == FileCategory.SOURCE
    assert FileClassifier.classify("app.tsx").category == FileCategory.SOURCE
    assert FileClassifier.classify("document.pdf").category == FileCategory.DOCUMENT
    assert FileClassifier.classify("notes.md").category == FileCategory.DOCUMENT
    assert FileClassifier.classify("report.docx").category == FileCategory.DOCUMENT
    assert FileClassifier.classify("data.csv").category == FileCategory.DOCUMENT
    assert FileClassifier.classify("config.yaml").category == FileCategory.CONFIG
    assert FileClassifier.classify(".env").category == FileCategory.CONFIG
    assert FileClassifier.classify("photo.png").category == FileCategory.BINARY
    assert FileClassifier.classify("app.exe").category == FileCategory.BINARY
    assert FileClassifier.classify("database.db").category == FileCategory.DATA


def test_extractability():
    assert FileClassifier.classify("main.py").is_text_extractable is True
    assert FileClassifier.classify("doc.pdf").is_text_extractable is True
    assert FileClassifier.classify("readme.txt").is_text_extractable is True
    assert FileClassifier.classify("icon.png").is_text_extractable is False
    assert FileClassifier.classify("binary.exe").is_text_extractable is False
