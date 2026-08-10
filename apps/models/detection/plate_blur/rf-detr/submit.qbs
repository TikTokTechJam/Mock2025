#!/bin/bash

#PBS -q normal
#PBS -l select=1:ncpus=1:ngpus=1:mem=8G
#PBS -l walltime=01:30:00
#PBS -N RFDETR_Train_Job
#PBS -o outputfiles/RFDETR_Train_Job.o
#PBS -e errorfiles/RFDETR_Train_Job.e

echo "=== GPU environment ==="
echo "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
echo "PATH=$PATH"

echo "=== NVIDIA devices ==="
ls -l /dev/nvidia* 2>&1

echo "=== nvidia-smi ==="
which nvidia-smi || true
nvidia-smi 2>&1 || true

module load python/3.11.5-gcc12

echo "Python:"
which python
python --version

echo "=== Existing PyTorch ==="
python - <<'PY'
try:
    import torch
    print("PyTorch:", torch.__version__)
    print("CUDA version:", torch.version.cuda)
    print("CUDA available:", torch.cuda.is_available())
    print("GPU count:", torch.cuda.device_count())
except Exception as e:
    print("PyTorch error:", repr(e))
PY

echo "pip:"
which pip
pip --version

pip install -U -q --user ultralytics
pip install -U -q --user roboflow
pip install -U -q --user rfdetr[train,loggers]
pip install --user --force-reinstall --no-cache-dir "numpy<2.4" "pandas<3"
python -m pip uninstall -y torch torchvision torchaudio
python -m pip install -U -q --user \
    torch==2.10.0 \
    torchvision==0.25.0 \
    torchaudio==2.10.0 \
    --index-url https://download.pytorch.org/whl/cu128
echo

cd /home/users/ntu/thuymaia/techjam/plate_blur/rf-detr
echo Running python file:
python train.py
echo
