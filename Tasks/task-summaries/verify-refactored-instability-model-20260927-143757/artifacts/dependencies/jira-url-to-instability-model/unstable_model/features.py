import re

import numpy as np
import pandas as pd

from .data import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS


URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
CODE_PATTERN = re.compile(r"[{};]|```|</?[a-z][^>]*>", re.IGNORECASE)


def text_features(text):
    text = str(text or "")
    lowered = text.casefold()
    words = re.findall(r"\b\w+\b", lowered)
    return {
        "text_log_chars": np.log1p(len(text)),
        "text_log_words": np.log1p(len(words)),
        "text_log_unique_words": np.log1p(len(set(words))),
        "text_question_marks": text.count("?"),
        "text_exclamation_marks": text.count("!"),
        "text_newlines": text.count("\n"),
        "text_has_url": int(bool(URL_PATTERN.search(text))),
        "text_has_code": int(bool(CODE_PATTERN.search(text))),
        "text_has_tbd_or_todo": int("tbd" in lowered or "todo" in lowered),
        "text_has_please": int("please" in lowered),
        "text_has_acceptance": int("acceptance" in lowered),
    }


class FeatureTransformer:
    def __init__(self):
        self.numeric_medians = {}
        self.means = {}
        self.scales = {}
        self.categories = {}
        self.feature_names = []

    def fit(self, frame):
        numeric = self._raw_numeric(frame, fit=True)
        self.means = numeric.mean().to_dict()
        scales = numeric.std(ddof=0).replace(0, 1.0)
        self.scales = scales.to_dict()
        self.categories = {
            column: sorted(frame[column].fillna("unknown").astype(str).unique())
            for column in CATEGORICAL_COLUMNS
        }
        self.feature_names = list(numeric.columns)
        for column in CATEGORICAL_COLUMNS:
            self.feature_names.extend(
                f"{column}={value}" for value in self.categories[column]
            )
        return self

    def transform(self, frame):
        numeric = self._raw_numeric(frame, fit=False)
        for column in numeric.columns:
            numeric[column] = (
                numeric[column] - self.means[column]
            ) / self.scales[column]
        numeric = numeric.replace([np.inf, -np.inf], 0.0).fillna(0.0)
        numeric = numeric.clip(lower=-20.0, upper=20.0)
        parts = [numeric.reset_index(drop=True)]
        for column in CATEGORICAL_COLUMNS:
            values = frame[column].fillna("unknown").astype(str)
            encoded = pd.DataFrame(
                {
                    f"{column}={category}": (values == category).astype(float)
                    for category in self.categories[column]
                }
            )
            parts.append(encoded.reset_index(drop=True))
        matrix = pd.concat(parts, axis=1)
        values = matrix[self.feature_names].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Feature transformation produced non-finite values.")
        return values

    def fit_transform(self, frame):
        return self.fit(frame).transform(frame)

    def _raw_numeric(self, frame, fit):
        numeric = pd.DataFrame(index=frame.index)
        for column in NUMERIC_COLUMNS:
            values = pd.to_numeric(frame[column], errors="coerce").replace(
                [np.inf, -np.inf], np.nan
            )
            if fit:
                median = values.median()
                self.numeric_medians[column] = (
                    0.0 if pd.isna(median) else float(median)
                )
            numeric[column] = values.fillna(self.numeric_medians[column])
        text = frame["model_text"].fillna("").map(text_features)
        text_frame = pd.DataFrame(text.tolist(), index=frame.index)
        return pd.concat([numeric, text_frame], axis=1).astype(float)

    def to_dict(self):
        return {
            "numeric_medians": self.numeric_medians,
            "means": self.means,
            "scales": self.scales,
            "categories": self.categories,
            "feature_names": self.feature_names,
        }

    @classmethod
    def from_dict(cls, values):
        transformer = cls()
        transformer.numeric_medians = values["numeric_medians"]
        transformer.means = values["means"]
        transformer.scales = values["scales"]
        transformer.categories = values["categories"]
        transformer.feature_names = values["feature_names"]
        return transformer
