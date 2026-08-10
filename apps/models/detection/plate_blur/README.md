# License Plate Detection

Singapore license-plate detector for the plate-blur stage of the PrivaStream
pipeline. Two candidate models are fine-tuned on the same dataset and compared
under one benchmark: **YOLO11n** (Ultralytics) and **RF-DETR Small** (Roboflow).

Single class: `license-plate`.

## Layout

```
plate_blur/
├── dataset.py            # download SG License Plate v2 from Roboflow (YOLO11 format)
├── benchmark.py          # AP + latency benchmark for both models on the test split
├── sg_plate_dataset/     # downloaded dataset (gitignored)
├── rf-detr/
│   ├── overview.md
│   ├── train.py          # fine-tune RF-DETR Small
│   ├── submit.qbs        # PBS job script (NSCC)
│   └── checkpoints/      # rf-detr-small.pth (base) + checkpoint_best_ema.pth (gitignored)
├── yolov11/
│   ├── train.py          # fine-tune YOLO11n
│   ├── submit.qbs        # PBS job script (NSCC)
│   ├── checkpoints/      # yolo11n.pt (base) + best.pt (fine-tuned) (gitignored)
│   └── runs/detect/train # Ultralytics training artifacts (curves, confusion matrix, results.csv)
└── outputfiles/          # benchmark job logs
```

## Requirements

```
roboflow
ultralytics
rfdetr[train,loggers]
python-dotenv
```

Reference environment (used for all numbers below): Python 3.11.5,
`torch==2.10.0+cu128`, `torchvision==0.25.0`, NVIDIA A100-SXM4-40GB.
See `*/submit.qbs` for the exact PBS/module setup on the HPC cluster.

## Dataset

`sg_plate_dataset` is [SG License Plate v2](https://universe.roboflow.com/car-plate-fcnrs/sg-license-plate-yqedo/dataset/2)
(CC BY 4.0) — 6,209 images in YOLO11 format, one class, letterboxed by Roboflow
to 640x640, with three augmented variants per source image (90° rotations,
0–20% crop, ±15° rotation, ±15% brightness/exposure, 0–2.5 px Gaussian blur,
0.1% salt-and-pepper noise).

Splits: **5,850 train / 328 val / 31 test** (33 test instances).

Put your Roboflow key in `.env` as `ROBOFLOW_API_KEY=...`, then:

```
python dataset.py
```

## Fine-tune

```
cd <model_folder>   # rf-detr or yolov11
python train.py
```

On the cluster, submit instead with `qsub submit.qbs` from the model folder.

Or download the trained checkpoints:
[OneDrive](https://entuedu-my.sharepoint.com/:f:/r/personal/thuymaia001_e_ntu_edu_sg/Documents/Techjam/rf-detr?d=w69372ce9c32d44d5aa0adfab2df746d1&csf=1&web=1&e=K1dawe)

### Key training settings

| | YOLO11n | RF-DETR Small |
|---|---|---|
| Starting weights | `yolo11n.pt` (COCO) | `rf-detr-small.pth` (COCO) |
| Train resolution | 640 | 512 |
| Epochs | 80 (all completed) | 100 requested, **23 completed** (1h30 walltime cap) |
| Batch | 16 | 4 x 4 grad-accum (effective 16) |
| LR / optimizer | `auto` (Ultralytics defaults, cosine off, `close_mosaic=10`) | 1e-4 |
| Best checkpoint | `best.pt` | `checkpoint_best_ema.pth` (EMA, best at epoch 15) |
| Best val mAP50:95 | 0.8217 (epoch 80) | 0.8543 (epoch 15) |

## Benchmark

```
python benchmark.py
```

Evaluates AP50 / AP50:95 on the test split and measures single-image latency
(batch size 1, 20 warm-up + 200 timed runs, images preloaded so disk I/O is
excluded, CUDA synchronised around each call, pre/post-processing included).
Both models are evaluated at 512x512, `conf=0.001`, `iou=0.5`.

> Point `RFDETR_MODEL_PATH` at the fine-tuned `rf-detr/checkpoints/checkpoint_best_ema.pth`
> before running — the constant currently in `benchmark.py` points at the base
> COCO checkpoint `rf-detr-small.pth`. The recorded run below used the
> fine-tuned EMA checkpoint.

### Results

Test split (31 images / 33 instances), A100-40GB, 512x512, batch 1
(source: `outputfiles/Benchmark_Job.o`):

| Model | AP50 | AP50:95 | Mean ms | Median ms | P95 ms | P99 ms | FPS |
|---|---|---|---|---|---|---|---|
| RF-DETR Small | 1.0000 | 0.8535 | 32.90 | 32.86 | 34.10 | 34.69 | 30.4 |
| YOLO11n | 0.9950 | 0.8299 | 9.59 | 9.58 | 9.65 | 9.82 | 104.3 |

YOLO11n reaches ~96% of RF-DETR's AP50:95 at **3.4x lower latency**.

## Notes on the work

### Improvement approaches tried

- Fine-tuned both a CNN one-stage detector (YOLO11n) and a DETR-style
  transformer detector (RF-DETR Small) from COCO weights on the same data, so
  accuracy and latency could be compared on one test set with one harness.
- Used the Roboflow-augmented dataset version (3 augmented variants per source
  image) rather than the raw images, for photometric/geometric robustness
  without writing a custom augmentation pipeline.
- Benchmarked RF-DETR at its recommended 512x512 resolution and used the EMA
  checkpoint rather than the plain best checkpoint (EMA was consistently ~0.01–0.02
  mAP50:95 ahead throughout training).
- Moved training to A100 PBS jobs (`submit.qbs`) after CPU/MPS runs proved
  impractical.
- Latency measured with warm-up, CUDA synchronisation, and preloaded images so
  the numbers reflect model cost rather than I/O or lazy CUDA init.

### Achieved target level

Both models are production-viable on accuracy for this dataset: AP50 ≥ 0.995 and
AP50:95 ≥ 0.83. On latency, YOLO11n at 9.6 ms mean / 9.65 ms P95 (104 FPS)
clears real-time 30 FPS video (33 ms budget) with room for the rest of the
pipeline; RF-DETR Small at 32.9 ms mean / 34.1 ms P95 sits right at the 30 FPS
budget and leaves none.

**YOLO11n (`yolov11/checkpoints/best.pt`) is the recommended model** for the
blur stage; RF-DETR Small is the higher-accuracy fallback for offline/batch
processing.

### Known remaining weaknesses

- **The test split is far too small to trust.** 31 images / 33 instances —
  RF-DETR's AP50 = 1.0000 is a small-sample artefact, not evidence of a perfect
  detector. Any AP difference under ~0.05 here is noise. A larger held-out set is
  needed before these numbers are quoted anywhere.
- **RF-DETR is under-trained**: the job hit the 1h30 walltime at epoch 23 of 100.
  Its val mAP50:95 was still trending up, so the reported accuracy is a lower
  bound.
- **Train/test domain is narrow**: daytime handheld phone photos of Singapore
  plates. Untested on motion blur, night/low-light, rain, oblique/far plates,
  dashcam and CCTV framing, and non-SG plate formats — all of which the streaming
  pipeline will see.
- **Possible source-image leakage**: the dataset ships 3 augmented variants per
  source image; if Roboflow split after augmentation, variants of the same photo
  can straddle train and test, inflating all metrics.
- **Annotation quality**: the test labels mix 2 segment annotations into a
  detection dataset (Ultralytics warns and drops the segments).
- **Resolution mismatch**: YOLO11n was trained at 640 but benchmarked at 512;
  its accuracy at its native resolution was not measured. RF-DETR's eval log also
  reports a 672 square resize despite `resolution=512`.
- **Latency was measured at `conf=0.001`**, which forces the maximum number of
  candidate boxes through post-processing — a worst case, not the deployment
  setting. Single GPU, batch 1, no TensorRT/FP16 export, no video decode.
- `rf-detr/train.py` passes `device="cpu"` to `model.train()`; the library
  overrode it to `cuda:0` in the recorded run, but the argument should be fixed
  before the next training run.

### Recommended runtime settings

From the YOLO11n validation curves (`yolov11/runs/detect/train/`):
peak F1 = 0.97 at conf 0.557; recall holds ~0.97 flat up to conf ≈ 0.6 and falls
off a cliff past 0.75.

For blurring, a missed plate is a privacy failure and a false positive is only a
blurred patch — so bias toward recall rather than peak F1:

- **Confidence threshold: 0.25** (0.20–0.40 is the safe band; recall is
  essentially flat across it). Do **not** use the F1-optimal 0.557 — it trades
  recall for precision in the wrong direction. Never run at 0.001 outside of
  benchmarking.
- **NMS IoU: 0.5.**
- **Inference size: 640** for YOLO11n (its training resolution); 512 for RF-DETR.
- **Dilate boxes by ~10% before blurring** to absorb localisation error —
  AP50:95 of ~0.83 means box edges are approximate even when detection succeeds.
- For video, add short-window temporal smoothing/tracking so a plate that drops
  below threshold in one frame stays blurred.
- Export to TensorRT/FP16 and batch frames if more headroom is needed; the
  current PyTorch FP32 numbers already fit 30 FPS on an A100, but not
  necessarily on smaller GPUs.
