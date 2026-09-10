import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
    default_project: str
    default_label_threshold: int
    train_fraction: float
    validation_fraction: float
    maximum_iterations: int
    learning_rate: float
    l2_regularization: float
    early_stopping_patience: int

    @property
    def test_fraction(self):
        return 1.0 - self.train_fraction - self.validation_fraction


def load_config(path):
    with Path(path).open(encoding="utf-8") as config_file:
        values = json.load(config_file)
    config = ModelConfig(**values)
    if config.train_fraction <= 0 or config.validation_fraction <= 0:
        raise ValueError("Train and validation fractions must be positive.")
    if config.test_fraction <= 0:
        raise ValueError("Train and validation fractions must leave a test set.")
    return config
