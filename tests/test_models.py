"""Smoke tests for core models."""

from testwise.models import TestClassification, TestwiseConfig


def test_classification_values() -> None:
    assert TestClassification.must_run.value == "must_run"
    assert TestClassification.should_run.value == "should_run"
    assert TestClassification.skip.value == "skip"


def test_default_config() -> None:
    config = TestwiseConfig()
    assert len(config.runners) == 1
    assert config.runners[0].name == "pytest"
    assert config.fallback_on_error is True
