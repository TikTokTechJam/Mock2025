import os
from dotenv import load_dotenv
from roboflow import Roboflow

load_dotenv()

api_key = os.getenv("ROBOFLOW_API_KEY")
rf = Roboflow(api_key=api_key)
project = rf.workspace("car-plate-fcnrs").project("sg-license-plate-yqedo")
version = project.version(2)
dataset = version.download(
    "yolov11",
    location="sg_plate_dataset"
)