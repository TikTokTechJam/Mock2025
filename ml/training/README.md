# Training

Place offline training, fine-tuning scripts, and their safe configuration here
when that work is approved. The shared dependency-free evaluation runner lives
in `ml/evaluation/`. This directory is not a runtime service and must not be
imported by `apps/api` during normal startup.
