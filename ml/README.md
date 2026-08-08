# Offline ML tooling

This directory is reserved for offline machine-learning development, including
training, fine-tuning, evaluation, and shared ML tooling owned by Issue #14.

Runtime API code must not import training-only dependencies by default. Keep
checkpoints, experiment outputs, and local caches outside Git.
