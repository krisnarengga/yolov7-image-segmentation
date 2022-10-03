import argparse
import os
import platform
import sys
from pathlib import Path

import torch
import torch.backends.cudnn as cudnn

#..... Tracker modules......
import skimage
from sort_count import *
import numpy as np
#...........................


FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # YOLOv5 root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH
ROOT = Path(os.path.relpath(ROOT, Path.cwd()))  # relative

from models.common import DetectMultiBackend
from utils.dataloaders import IMG_FORMATS, VID_FORMATS, LoadImages, LoadStreams
from utils.general import (LOGGER, Profile, check_file, check_img_size, check_imshow, check_requirements, colorstr, cv2,
                           increment_path, non_max_suppression, print_args, scale_coords, strip_optimizer, xyxy2xywh)
from utils.plots import Annotator, colors, save_one_box
from utils.segment.general import process_mask, scale_masks
from utils.segment.plots import plot_masks
from utils.torch_utils import select_device, smart_inference_mode


area1_pointA = (250,300)
area1_pointB = (650,300)
area1_pointC = (250,350)
area1_pointD = (650,350)

array_ids = []
counting = 0
modulo_counting = 0

#............................... Tracker Functions ............................
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        
def onSegment(p, q, r):
    if ((q.x <= max(p.x, r.x)) and (q.x >= min(p.x, r.x)) and
            (q.y <= max(p.y, r.y)) and (q.y >= min(p.y, r.y))):
        return True
    return False

def orientation(p, q, r):
    val = (float(q.y - p.y) * (r.x - q.x)) - (float(q.x - p.x) * (r.y - q.y))
    if (val > 0):
        return 1
    elif (val < 0):
        return 2
    else:
        return 0

def Intersection(p1, q1, p2, q2):
    o1 = orientation(p1, q1, p2)
    o2 = orientation(p1, q1, q2)
    o3 = orientation(p2, q2, p1)
    o4 = orientation(p2, q2, q1)
    if ((o1 != o2) and (o3 != o4)):
        return True
    if ((o1 == 0) and onSegment(p1, p2, q1)):
        return True
    if ((o2 == 0) and onSegment(p1, q2, q1)):
        return True
    if ((o3 == 0) and onSegment(p2, p1, q2)):
        return True
    if ((o4 == 0) and onSegment(p2, q1, q2)):
        return True
    return False
#..............................................................................


@smart_inference_mode()
def run(
        weights=ROOT / 'yolov5s-seg.pt',  # model.pt path(s)
        source=ROOT / 'data/images',  # file/dir/URL/glob, 0 for webcam
        data=ROOT / 'data/coco128.yaml',  # dataset.yaml path
        imgsz=(640, 640),  # inference size (height, width)
        conf_thres=0.25,  # confidence threshold
        iou_thres=0.45,  # NMS IOU threshold
        max_det=1000,  # maximum detections per image
        device='',  # cuda device, i.e. 0 or 0,1,2,3 or cpu
        view_img=False,  # show results
        save_txt=False,  # save results to *.txt
        save_conf=False,  # save confidences in --save-txt labels
        save_crop=False,  # save cropped prediction boxes
        nosave=False,  # do not save images/videos
        classes=None,  # filter by class: --class 0, or --class 0 2 3
        agnostic_nms=False,  # class-agnostic NMS
        augment=False,  # augmented inference
        visualize=False,  # visualize features
        update=False,  # update all models
        project=ROOT / 'runs/predict-seg',  # save results to project/name
        name='exp',  # save results to project/name
        exist_ok=False,  # existing project/name ok, do not increment
        line_thickness=3,  # bounding box thickness (pixels)
        hide_labels=False,  # hide labels
        hide_conf=False,  # hide confidences
        half=False,  # use FP16 half-precision inference
        dnn=False,  # use OpenCV DNN for ONNX inference
        trk = False,
):  

    #.... Initialize SORT .... 
        
    sort_max_age = 5 
    sort_min_hits = 2
    sort_iou_thresh = 0.2
    person_up_count =0
    person_down_count =0
    sort_tracker = Sort(max_age=sort_max_age,
                        min_hits=sort_min_hits,
                        iou_threshold=sort_iou_thresh) 
    #......................... 

    source = str(source)
    save_img = not nosave and not source.endswith('.txt')  # save inference images
    is_file = Path(source).suffix[1:] in (IMG_FORMATS + VID_FORMATS)
    is_url = source.lower().startswith(('rtsp://', 'rtmp://', 'http://', 'https://'))
    webcam = source.isnumeric() or source.endswith('.txt') or (is_url and not is_file)
    if is_url and is_file:
        source = check_file(source)  # download

    # Directories
    save_dir = increment_path(Path(project) / name, exist_ok=exist_ok)  # increment run
    (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    # Load model
    device = select_device(device)
    model = DetectMultiBackend(weights, device=device, dnn=dnn, data=data, fp16=half)
    stride, names, pt = model.stride, model.names, model.pt
    imgsz = check_img_size(imgsz, s=stride)  # check image size

    # Dataloader
    if webcam:
        view_img = check_imshow()
        cudnn.benchmark = True  # set True to speed up constant image size inference
        dataset = LoadStreams(source, img_size=imgsz, stride=stride, auto=pt)
        bs = len(dataset)  # batch_size
    else:
        dataset = LoadImages(source, img_size=imgsz, stride=stride, auto=pt)
        bs = 1  # batch_size
    vid_path, vid_writer = [None] * bs, [None] * bs

    # Run inference
    model.warmup(imgsz=(1 if pt else bs, 3, *imgsz))  # warmup
    seen, windows, dt = 0, [], (Profile(), Profile(), Profile())
    
    count_vehicle = 0
    
    for path, im, im0s, vid_cap, s in dataset:
        height_img,width_img,ch_img = im0s.shape
        line_pt_1 = (0, height_img // 2)
        line_pt_2 = (width_img, height_img // 2)
        with dt[0]:
            im = torch.from_numpy(im).to(device)
            im = im.half() if model.fp16 else im.float()  # uint8 to fp16/32
            im /= 255  # 0 - 255 to 0.0 - 1.0
            if len(im.shape) == 3:
                im = im[None]  # expand for batch dim

        # Inference
        with dt[1]:
            visualize = increment_path(save_dir / Path(path).stem, mkdir=True) if visualize else False
            pred, out = model(im, augment=augment, visualize=visualize)
            proto = out[1]

        # NMS
        with dt[2]:
            pred = non_max_suppression(pred, conf_thres, iou_thres, classes, agnostic_nms, max_det=max_det, nm=32)

        # Second-stage classifier (optional)
        # pred = utils.general.apply_classifier(pred, classifier_model, im, im0s)

        # Process predictions
        for i, det in enumerate(pred):  # per image
            seen += 1
            if webcam:  # batch_size >= 1
                p, im0, frame = path[i], im0s[i].copy(), dataset.count
                s += f'{i}: '
            else:
                p, im0, frame = path, im0s.copy(), getattr(dataset, 'frame', 0)

            p = Path(p)  # to Path
            save_path = str(save_dir / p.name)  # im.jpg
            txt_path = str(save_dir / 'labels' / p.stem) + ('' if dataset.mode == 'image' else f'_{frame}')  # im.txt
            s += '%gx%g ' % im.shape[2:]  # print string
            gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh
            imc = im0.copy() if save_crop else im0  # for save_crop
            annotator = Annotator(im0, line_width=line_thickness, example=str(names))
            
            centers = []
            ids = []
            if len(det):
                masks = process_mask(proto[i], det[:, 6:], det[:, :4], im.shape[2:], upsample=True)  # HWC

                # Rescale boxes from img_size to im0 size
                det[:, :4] = scale_coords(im.shape[2:], det[:, :4], im0.shape).round()

                # Print results
                for c in det[:, 5].unique():
                    n = (det[:, 5] == c).sum()  # detections per class
                    s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string

                # Mask plotting ----------------------------------------------------------------------------------------
                mcolors = [colors(int(6), True) for cls in det[:, 5]]
                im_masks = plot_masks(im[i], masks, mcolors)  # image with masks shape(imh,imw,3)
                annotator.im = scale_masks(im.shape[2:], im_masks, im0.shape)  # scale to original h, w
                # Mask plotting ----------------------------------------------------------------------------------------

                if trk:
                    #Tracking ----------------------------------------------------
                    dets_to_sort = np.empty((0,6))
                    for x1,y1,x2,y2,conf,detclass in det[:, :6].cpu().detach().numpy():
                        dets_to_sort = np.vstack((dets_to_sort, 
                                        np.array([x1, y1, x2, y2, 
                                                    conf, detclass])))

                    tracked_dets = sort_tracker.update(dets_to_sort)
                    tracks = sort_tracker.getTrackers()

                    for track in tracks:
                        index1 = -1
                        index2 = -2
                        if len(track.centroids) == 1:
                            index2 = -1
                        interseted = Intersection(Point(track.centroids[index1][0], 
                                                            track.centroids[index1][1]),
                                                        Point(track.centroids[index2][0], 
                                                                track.centroids[index2][1]),
                                                        Point(line_pt_1[0],line_pt_1[1]), 
                                                        Point(line_pt_2[0], line_pt_2[1]))
                        if (interseted == True):
                            if track.centroids[index2][1] > track.centroids[index1][1]:
                                person_up_count+=1
                            
                            else:
                                person_down_count+=1
                        
                        annotator.draw_trk(line_thickness,track)
                    
                    
                    if len(tracked_dets)>0:
                        bbox_xyxy = tracked_dets[:,:4]
                        identities = tracked_dets[:, 8]
                        categories = tracked_dets[:, 4]
                        centers,ids = annotator.draw_id(bbox_xyxy, identities, categories, names)
                        
                        #bbox = bbox_xyxy
                        #offset=(0, 0)
                    
                        
                        '''
                        for i, box in enumerate(bbox):
                            x1, y1, x2, y2 = [int(i) for i in box]
                            x1 += offset[0]
                            x2 += offset[0]
                            y1 += offset[1]
                            y2 += offset[1]
                            cat = int(categories[i]) if categories is not None else 0
                            id = int(identities[i]) if identities is not None else 0
                            #data = (int((box[0]+box[2])/2),(int((box[1]+box[3])/2)))
                            label = str(id)
                            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                            #cv2.rectangle(im0, (x1, y1 - 20), (x1 + w, y1), (255,144,30), -1)
                            cv2.putText(im0, label, (x1, y1 - 5),cv2.FONT_HERSHEY_SIMPLEX, 0.6, [255, 255, 255], 1)
                            
                            midpoint_x = x1+((x2-x1)/2)
                            midpoint_y = y1+((y2-y1)/2)
                            center_point = (int(midpoint_x),int(midpoint_y))
                            cv2.circle(im, center_point, radius=1, color=(0,255,0),thickness=2)
                        '''
                        
                        #for xy in bbox_xyxy:
                            #print(xy)
                            #cv2.circle(im0,(xy[0],xy[1]),radius=1,color=(0,255,0),thickness=2)   
                        #c1, c2 = (int(bbox_xyxy[0]), int(bbox_xyxy[1])), (int(bbox_xyxy[2]), int(bbox_xyxy[3]))
                        #print(bbox_xyxy)
                        #midpoint_x = c1[0]+((c2[0]-c1[0])/2)
                        #midpoint_y = c2[1]                        
                        
                        #midpoint_x = x1+((x2-x1)/2)
                        #midpoint_y = y1+((y2-y1)/2)
                        #center_point = (int(midpoint_x),int(midpoint_y))
                        #midpoint_color = (0,255,0)
                        #cv2.circle(img,center_point,radius=1,color=midpoint_color,thickness=2)

                        '''
                        if (midpoint_x > area1_pointA[0] and midpoint_x < area1_pointD[0]) and (midpoint_y > area1_pointA[1] and midpoint_y < area1_pointD[1]):
                            
                            midpoint_color = (0,0,255)
                            print('Kategori : '+str(cat))
                            
                            #add vehicles counting
                            if len(array_ids) > 0:
                                if id not in array_ids:
                                    array_ids.append(id)
                            else:
                                array_ids.append(id)
                        '''
            
            
                # Write results
                for *xyxy, conf, cls in reversed(det[:, :6]):
                    if save_txt:  # Write to file
                        xywh = (xyxy2xywh(torch.tensor(xyxy).view(1, 4)) / gn).view(-1).tolist()  # normalized xywh
                        line = (cls, *xywh, conf) if save_conf else (cls, *xywh)  # label format
                        with open(f'{txt_path}.txt', 'a') as f:
                            f.write(('%g ' * len(line)).rstrip() % line + '\n')

                    if save_img or save_crop or view_img:  # Add bbox to image
                        c = int(cls)  # integer class
                        label = None if hide_labels else (names[c] if hide_conf else f'{names[c]} {conf:.2f}')
                        annotator.box_label(xyxy, label, color=colors(c, True))
                    if save_crop:
                        save_one_box(xyxy, imc, file=save_dir / 'crops' / names[c] / f'{p.stem}.jpg', BGR=True)



            # Stream results
            im0 = annotator.result()
            
            if len(centers)>0:
                
                #print(center_and_ids)
                
                the_id = 0
                center = (0,0)
                
                i = 0
                for center in centers:
                    #print(center)
                    #print(ids[i])
                    the_id = ids[i]
                    
                    
                    cv2.circle(im0, center, radius=1, color=(0,255,0),thickness=2)
                    
                    if (center[0] > area1_pointA[0] and center[0] < area1_pointD[0]) and (center[1] > area1_pointA[1] and center[1] < area1_pointD[1]):
            
                        midpoint_color = (0,0,255)
                        cv2.circle(im0, center, radius=1, color=midpoint_color,thickness=2)
                        #print('Kategori : '+str(cat))
                        
                        #add vehicles counting
                        if len(array_ids) > 0:
                            if the_id not in array_ids:
                                array_ids.append(the_id)
                        else:
                            array_ids.append(the_id)
                    
                    i = i + 1
                    
            
                if (count_vehicle == 0):
                    counting = len(array_ids)
                else:
                    if (counting < 100):
                        counting = len(array_ids)
                    else:
                        counting = modulo_counting + len(array_ids)
                        if(len(array_ids)%100 == 0):
                            modulo_counting = modulo_counting + 100
                            array_ids.clear()
                
            cv2.line(im0,area1_pointA,area1_pointB,(0,255,0),2)
            cv2.line(im0,area1_pointC,area1_pointD,(0,255,0),2)
            
            color = (0,255,0)
            thickness = 2
            fontScale = 1
            font = cv2.FONT_HERSHEY_SIMPLEX
            org = (20,450)
            
            cv2.putText(im0, 'Vehicle Counting = '+str(counting), org, font, fontScale, color, thickness, cv2.LINE_AA)            

            
            if view_img:
                if platform.system() == 'Linux' and p not in windows:
                    windows.append(p)
                    cv2.namedWindow(str(p), cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)  # allow window resize (Linux)
                    cv2.resizeWindow(str(p), im0.shape[1], im0.shape[0])
                cv2.imshow(str(p), im0)
                cv2.waitKey(1)  # 1 millisecond

            # Save results (image with detections)
            if save_img:
                if dataset.mode == 'image':
                    cv2.imwrite(save_path, im0)
                else:  # 'video' or 'stream'
                    if vid_path[i] != save_path:  # new video
                        vid_path[i] = save_path
                        if isinstance(vid_writer[i], cv2.VideoWriter):
                            vid_writer[i].release()  # release previous video writer
                        if vid_cap:  # video
                            fps = vid_cap.get(cv2.CAP_PROP_FPS)
                            w = int(vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            h = int(vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        else:  # stream
                            fps, w, h = 30, im0.shape[1], im0.shape[0]
                        save_path = str(Path(save_path).with_suffix('.mp4'))  # force *.mp4 suffix on results videos
                        vid_writer[i] = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
                    vid_writer[i].write(im0)

        # Print time (inference-only)
        LOGGER.info(f"{s}{'' if len(det) else '(no detections), '}{dt[1].dt * 1E3:.1f}ms")

    # Print results
    t = tuple(x.t / seen * 1E3 for x in dt)  # speeds per image
    LOGGER.info(f'Speed: %.1fms pre-process, %.1fms inference, %.1fms NMS per image at shape {(1, 3, *imgsz)}' % t)
    if save_txt or save_img:
        s = f"\n{len(list(save_dir.glob('labels/*.txt')))} labels saved to {save_dir / 'labels'}" if save_txt else ''
        LOGGER.info(f"Results saved to {colorstr('bold', save_dir)}{s}")
    if update:
        strip_optimizer(weights[0])  # update model (to fix SourceChangeWarning)


def parse_opt():
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', nargs='+', type=str, default=ROOT / 'yolov5s-seg.pt', help='model path(s)')
    parser.add_argument('--source', type=str, default=ROOT / 'data/images', help='file/dir/URL/glob, 0 for webcam')
    parser.add_argument('--data', type=str, default=ROOT / 'data/coco128.yaml', help='(optional) dataset.yaml path')
    parser.add_argument('--imgsz', '--img', '--img-size', nargs='+', type=int, default=[640], help='inference size h,w')
    parser.add_argument('--conf-thres', type=float, default=0.45, help='confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.45, help='NMS IoU threshold')
    parser.add_argument('--max-det', type=int, default=1000, help='maximum detections per image')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', action='store_true', help='show results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--save-crop', action='store_true', help='save cropped prediction boxes')
    parser.add_argument('--nosave', action='store_true', help='do not save images/videos')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --classes 0, or --classes 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--visualize', action='store_true', help='visualize features')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default=ROOT / 'runs/predict-seg', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--line-thickness', default=1, type=int, help='bounding box thickness (pixels)')
    parser.add_argument('--hide-labels', default=False, action='store_true', help='hide labels')
    parser.add_argument('--hide-conf', default=False, action='store_true', help='hide confidences')
    parser.add_argument('--half', action='store_true', help='use FP16 half-precision inference')
    parser.add_argument('--dnn', action='store_true', help='use OpenCV DNN for ONNX inference')
    parser.add_argument('--trk', action='store_true', help='Apply Sort Tracking')
    opt = parser.parse_args()
    opt.imgsz *= 2 if len(opt.imgsz) == 1 else 1  # expand
    print_args(vars(opt))
    return opt


def main(opt):
    check_requirements(exclude=('tensorboard', 'thop'))
    run(**vars(opt))


if __name__ == "__main__":
    opt = parse_opt()
    main(opt)
