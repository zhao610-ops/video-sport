"""在已有球员分析上追加足球检测与图像轨迹，单独保存足球数据。"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from sports.common.ball_tracking import ObservedBallTracker, tile_origins, suppress_duplicates
from sports.common.ball_data import file_sha256


def track_ball(analysis_path, output_dir=None, device='auto', max_frames=None, confidence=.25,
               model_path=None, save_video=False):
    import cv2
    from ultralytics import YOLO
    from examples.soccer.main import resolve_device, BALL_DETECTION_MODEL_PATH
    from sports.common.analysis import MappingSettings, fit_mapping, map_position
    from sports.configs.soccer import SoccerPitchConfiguration

    analysis_path = Path(analysis_path)
    with open(analysis_path, encoding='utf-8') as stream:
        analysis = json.load(stream)
    if analysis.get('schema_version') != '1.0' or not analysis.get('frames'):
        raise ValueError('需要非空的球员分析结果')
    if not 0 < confidence <= 1 or max_frames is not None and max_frames <= 0:
        raise ValueError('足球检测参数无效')
    target = Path(output_dir or analysis_path.parent/'ball')
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise FileExistsError('足球结果目录非空，请选择新目录')
    source = Path(analysis['metadata']['source_video'])
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError('无法读取对应原视频')
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    if abs(fps-analysis['metadata']['fps']) > .01 or {'width': width, 'height': height} != analysis['metadata']['image_size']:
        capture.release()
        raise ValueError('视频帧率或尺寸与球员分析不一致')
    device = resolve_device(device)
    model_path = model_path or BALL_DETECTION_MODEL_PATH
    if not Path(model_path).is_file():
        capture.release()
        raise ValueError('本地足球检测权重不存在，请先准备模型文件')
    model = YOLO(model_path).to(device)
    if 'ball' not in str(model.names[0]).casefold():
        capture.release()
        raise ValueError('指定权重的第0类不是足球，请使用配套足球检测模型')
    config = SoccerPitchConfiguration(**analysis['metadata']['template_cm'])
    settings = MappingSettings(**analysis['metadata']['mapping_settings'])
    tracker = ObservedBallTracker(width, height, min_confidence=confidence)
    wanted = analysis['frames'][:max_frames] if max_frames else analysis['frames']
    by_index = {f['frame_index']: f for f in wanted}
    records, previous_histogram, sink = [], None, None
    if save_video:
        sink = cv2.VideoWriter(str(target/'ball-review.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
        if not sink.isOpened():
            capture.release()
            raise ValueError('无法创建足球核对视频')
    status = 'error'
    try:
        for index in range(max(by_index)+1):
            ok, image = capture.read()
            if not ok:
                break
            if index not in by_index:
                continue
            tiles, origins = [], []
            for y in tile_origins(height):
                for x in tile_origins(width):
                    tiles.append(image[y:y+640, x:x+640])
                    origins.append((x, y))
            candidates = []
            batch = 1 if device == 'cpu' else 4
            for start in range(0, len(tiles), batch):
                results = model.predict(tiles[start:start+batch], imgsz=640, conf=confidence,
                                        iou=.1, verbose=False, device=device)
                for offset, result in enumerate(results):
                    ox, oy = origins[start+offset]
                    for box, score, class_id in zip(result.boxes.xyxy.cpu().tolist(),
                                                   result.boxes.conf.cpu().tolist(), result.boxes.cls.cpu().tolist()):
                        if int(class_id) != 0:
                            continue
                        candidates.append({'bbox_xyxy': [max(0., box[0]+ox), max(0., box[1]+oy),
                                                         min(float(width), box[2]+ox), min(float(height), box[3]+oy)],
                                           'confidence': float(score)})
            candidates = suppress_duplicates(candidates)
            thumbnail = cv2.resize(image, (64, 36))
            histogram = cv2.calcHist([thumbnail], [0, 1, 2], None, [8, 8, 8], [0, 256]*3)
            cv2.normalize(histogram, histogram)
            scene_changed = previous_histogram is not None and cv2.compareHist(
                previous_histogram, histogram, cv2.HISTCMP_BHATTACHARYYA) > .65
            previous_histogram = histogram
            record = tracker.update(index, candidates, scene_changed=scene_changed)
            record.update(frame_index=index, timestamp_s=by_index[index]['timestamp_s'],
                          candidate_count=len(candidates), scene_changed=bool(scene_changed),
                          x_norm=None, y_norm=None, projection_valid=False,
                          projection_reason='ball_not_detected', grounded_verified=False)
            if record['detected']:
                raw = by_index[index].get('keypoints')
                matrix = None
                if raw and by_index[index]['mapping']['valid']:
                    # 当前帧重新拟合；失效时不沿用之前的球场矩阵。
                    cv2.setRNGSeed(0)
                    matrix, _ = fit_mapping(raw['xy'], raw['confidence'], config, settings)
                x, y, valid, reason = map_position([record['image_x'], record['image_y']], matrix, config)
                record.update(x_norm=x, y_norm=y, projection_valid=valid, projection_reason=reason)
            records.append(record)
            if sink:
                annotated = image.copy()
                if record['detected']:
                    x, y = round(record['image_x']), round(record['image_y'])
                    cv2.circle(annotated, (x, y), 14, (0, 240, 255), 2)
                    cv2.putText(annotated, f"ball {record['confidence']:.2f} seg {record['segment_id']}",
                                (max(0, x-45), max(18, y-20)), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 240, 255), 1)
                cv2.putText(annotated, f"frame {index} {record['tracking_status']}",
                            (20, 35), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 240, 255), 2)
                sink.write(annotated)
            if len(records) % 25 == 0:
                print(f'足球检测：{len(records)}/{len(wanted)} 帧', flush=True)
        status = 'complete' if len(records) == len(analysis['frames']) else 'incomplete'
    finally:
        capture.release()
        if sink:
            sink.release()
        payload = {'schema_version': 'ball-1.0',
                   'metadata': {'source_analysis_sha256': file_sha256(analysis_path),
                                'source_video_sha256': file_sha256(source), 'fps': fps,
                                'image_size': {'width': width, 'height': height},
                                'device': device, 'model_name': Path(model_path).name,
                                'confidence_threshold': confidence, 'slice_size': 640, 'slice_overlap': 128,
                                'association': {'max_gap_frames': 5, 'gate_fraction_per_frame': .06},
                                'coordinate_note': '图像中心经地面单应性投影；未验证球是否贴地。空中球的投影不是实际落地点或真实场地位置，不支持球权、传球或速度判断。'},
                   'summary': {'status': status, 'frames': len(records),
                               'detected_frames': sum(r['detected'] for r in records),
                               'projected_frames': sum(r['projection_valid'] for r in records),
                               'tracking_status_counts': dict(Counter(r['tracking_status'] for r in records))},
                   'frames': records}
        temporary = target/'ball.json.tmp'
        with open(temporary, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False, indent=2)
        temporary.replace(target/'ball.json')
        fields = ['frame_index', 'timestamp_s', 'detected', 'confidence', 'image_x', 'image_y',
                  'segment_id', 'tracking_status', 'x_norm', 'y_norm', 'projection_valid',
                  'projection_reason', 'grounded_verified', 'candidate_count', 'scene_changed']
        with open(target/'ball.csv', 'w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(records)
    print(f'足球结果：{target.resolve()}；{payload["summary"]}', flush=True)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='为已分析视频追加足球检测与真实观测轨迹')
    parser.add_argument('--analysis', required=True)
    parser.add_argument('--output-dir')
    parser.add_argument('--device', default='auto', choices=['auto', 'mps', 'cpu', 'cuda'])
    parser.add_argument('--max-frames', type=int)
    parser.add_argument('--confidence', type=float, default=.25)
    parser.add_argument('--model')
    parser.add_argument('--save-video', action='store_true')
    args = parser.parse_args()
    track_ball(args.analysis, args.output_dir, args.device, args.max_frames, args.confidence, args.model, args.save_video)
