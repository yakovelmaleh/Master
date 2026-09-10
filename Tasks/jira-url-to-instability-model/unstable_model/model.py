import numpy as np


def sigmoid(values):
    values = np.clip(values, -35, 35)
    return 1.0 / (1.0 + np.exp(-values))


def weighted_log_loss(labels, probabilities, weights):
    probabilities = np.clip(probabilities, 1e-9, 1 - 1e-9)
    losses = -(
        labels * np.log(probabilities)
        + (1 - labels) * np.log(1 - probabilities)
    )
    return float(np.average(losses, weights=weights))


class StableLogisticRegression:
    def __init__(
        self,
        learning_rate,
        maximum_iterations,
        l2_regularization,
        early_stopping_patience,
    ):
        self.learning_rate = learning_rate
        self.maximum_iterations = maximum_iterations
        self.l2_regularization = l2_regularization
        self.early_stopping_patience = early_stopping_patience
        self.coefficients = None
        self.intercept = 0.0
        self.iterations = 0
        self.best_validation_loss = None

    @staticmethod
    def class_weights(labels):
        positive_count = max(1, int(np.sum(labels)))
        negative_count = max(1, len(labels) - positive_count)
        total = len(labels)
        return np.where(
            labels == 1,
            total / (2.0 * positive_count),
            total / (2.0 * negative_count),
        )

    def fit(self, features, labels, validation_features, validation_labels):
        labels = np.asarray(labels, dtype=float)
        validation_labels = np.asarray(validation_labels, dtype=float)
        weights = self.class_weights(labels)
        validation_weights = self.class_weights(validation_labels)
        self.coefficients = np.zeros(features.shape[1], dtype=float)
        self.intercept = 0.0
        best_coefficients = self.coefficients.copy()
        best_intercept = self.intercept
        best_loss = float("inf")
        stale_iterations = 0

        for iteration in range(1, self.maximum_iterations + 1):
            logits = np.einsum(
                "ij,j->i", features, self.coefficients, optimize=False
            )
            probabilities = sigmoid(logits + self.intercept)
            errors = (probabilities - labels) * weights
            normalization = max(1.0, float(np.sum(weights)))
            coefficient_gradient = (
                np.einsum(
                    "ij,i->j", features, errors, optimize=False
                )
                / normalization
                + self.l2_regularization * self.coefficients
            )
            intercept_gradient = float(np.sum(errors) / normalization)
            coefficient_gradient = np.clip(
                coefficient_gradient, -10.0, 10.0
            )
            intercept_gradient = float(
                np.clip(intercept_gradient, -10.0, 10.0)
            )
            current_learning_rate = self.learning_rate / np.sqrt(iteration)
            self.coefficients -= (
                current_learning_rate * coefficient_gradient
            )
            self.intercept -= current_learning_rate * intercept_gradient

            if not np.isfinite(self.coefficients).all() or not np.isfinite(
                self.intercept
            ):
                raise FloatingPointError(
                    "Training produced non-finite model parameters."
                )

            validation_probability = self.predict_proba(validation_features)
            validation_loss = weighted_log_loss(
                validation_labels,
                validation_probability,
                validation_weights,
            )
            if validation_loss < best_loss - 1e-6:
                best_loss = validation_loss
                best_coefficients = self.coefficients.copy()
                best_intercept = self.intercept
                stale_iterations = 0
            else:
                stale_iterations += 1
                if stale_iterations >= self.early_stopping_patience:
                    self.iterations = iteration
                    break
        else:
            self.iterations = self.maximum_iterations

        self.coefficients = best_coefficients
        self.intercept = best_intercept
        self.best_validation_loss = best_loss
        return self

    def predict_proba(self, features):
        logits = np.einsum(
            "ij,j->i", features, self.coefficients, optimize=False
        )
        return sigmoid(logits + self.intercept)
