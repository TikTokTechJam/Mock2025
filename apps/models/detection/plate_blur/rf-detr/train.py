import os
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"

from pathlib import Path
import torch
from rfdetr import RFDETRSmall

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
torch.set_default_device(device)

DATASET_DIR = Path("../sg_plate_dataset")
OUTPUT_DIR = Path("checkpoints")
PRETRAIN_WEIGHTS = "checkpoints/rf-detr-small.pth"

RESOLUTION = 512
EPOCHS = 100

# Adjust according to your GPU
BATCH_SIZE = 4
GRAD_ACCUM_STEPS = 4
LEARNING_RATE = 1e-4
NUM_WORKERS = 0

def main():
    model = RFDETRSmall(resolution=RESOLUTION, pretrain_weights=PRETRAIN_WEIGHTS)

    model.train(
        device="cpu",
        dataset_dir=str(DATASET_DIR),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        grad_accum_steps=GRAD_ACCUM_STEPS,
        lr=LEARNING_RATE,
        resolution=RESOLUTION,
        num_workers=NUM_WORKERS,
        output_dir=str(OUTPUT_DIR),
    )
    
if __name__ == "__main__":
    main()