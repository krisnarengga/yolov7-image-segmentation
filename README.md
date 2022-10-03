# yolov7-image-segmentation
This project is demonstrating simple traffic counting on toll road or highway using image segmentation technique with low light environment

This app is based on YOLOV7 object detection library engine from WongKinYiu repository on https://github.com/WongKinYiu/yolov7

And based on image segmentation and tracking github project from RizwanMunawar on https://github.com/RizwanMunawar/yolov7-segmentation.git

Run this command to run the app : python segment/predict_counting.py --weights yolov7-seg.pt --source 120.mp4 --view-img --nosave --trk

Notes: You can download yolov7-seg from https://github.com/RizwanMunawar/yolov7-segmentation/releases/download/yolov7-segmentation/yolov7-seg.pt

App Demo: https://www.youtube.com/watch?v=o3imTspjnn8

Sample Video: https://drive.google.com/file/d/1irx1XrYUmA34QNKfuX8KSRPPAOB5SYtc/view?usp=sharing
