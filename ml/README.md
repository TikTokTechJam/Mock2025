# Offline ML tooling

This directory contains offline machine-learning development tooling. The
dependency-free benchmark runner under `evaluation/` is owned by Issue #15;
training and fine-tuning remain separate offline work.

Runtime API code must not import training-only dependencies by default. Keep
checkpoints, experiment outputs, and local caches outside Git.
