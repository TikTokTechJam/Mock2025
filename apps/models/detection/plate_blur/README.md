Requirements:
```
roboflow
ultralytics
rfdetr[train,loggers]
```

Download dataset:
```
python dataset.py
```

Fine-tune:
```
cd <model_folder>
```

```
python train.py
```

Or download checkpoints:
[OneDrive](https://entuedu-my.sharepoint.com/:f:/r/personal/thuymaia001_e_ntu_edu_sg/Documents/Techjam/rf-detr?d=w69372ce9c32d44d5aa0adfab2df746d1&csf=1&web=1&e=K1dawe)

Benchmarking:
```
python benchmark.py
```