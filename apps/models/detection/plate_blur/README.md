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

Benchmarking:
```
python benchmark.py
```