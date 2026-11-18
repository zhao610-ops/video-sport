"""核验并读取足球附加结果，避免混用不同视频或旧的球场映射。"""

import hashlib
import json
import math
from pathlib import Path


NOTE = '球场坐标是球的图像中心向地面的近似投影，未验证球是否贴地；不代表空中球真实位置或落地点。'


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_ball_data(path, analysis_path, video_path, analysis):
    path = Path(path)
    missing = {'available': False, 'reason': '尚未生成足球检测结果', 'frames': [], 'note': NOTE}
    if not path.is_file():
        return missing
    try:
        with open(path, encoding='utf-8') as stream:
            data = json.load(stream)
        if data['schema_version'] != 'ball-1.0' or data['summary']['status'] != 'complete':
            raise ValueError('足球检测未完整完成')
        meta = data['metadata']
        if (meta['source_analysis_sha256'] != file_sha256(analysis_path)
                or meta['source_video_sha256'] != file_sha256(video_path)):
            raise ValueError('足球结果与当前视频或球场映射不匹配，请重新生成')
        if len(data['frames']) != len(analysis['frames']):
            raise ValueError('足球结果帧数与球员分析不一致')
        width, height = meta['image_size']['width'], meta['image_size']['height']
        frames = []
        for row, frame in zip(data['frames'], analysis['frames']):
            if (type(row['frame_index']) is not int or type(row['timestamp_s']) not in (int, float)
                    or not math.isfinite(row['timestamp_s'])
                    or row['frame_index'] != frame['frame_index'] or row['timestamp_s'] != frame['timestamp_s']
                    or type(row['detected']) is not bool or type(row['projection_valid']) is not bool):
                raise ValueError('足球帧编号、时间或标记无效')
            if row['detected']:
                values = [row['image_x'], row['image_y'], row['confidence'], *row['bbox_xyxy']]
                if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                    raise ValueError('足球图像坐标包含无效数值')
                if not (0 <= row['image_x'] <= width and 0 <= row['image_y'] <= height
                        and 0 <= row['confidence'] <= 1 and len(row['bbox_xyxy']) == 4
                        and type(row['segment_id']) is int and row['segment_id'] > 0):
                    raise ValueError('足球检测记录无效')
                x1, y1, x2, y2 = row['bbox_xyxy']
                if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height
                        and abs(row['image_x']-(x1+x2)/2) < 1e-5
                        and abs(row['image_y']-(y1+y2)/2) < 1e-5):
                    raise ValueError('足球检测框与中心坐标不一致')
            elif row['projection_valid'] or any(row[key] is not None for key in ('image_x', 'image_y', 'confidence', 'bbox_xyxy', 'segment_id', 'x_norm', 'y_norm')):
                raise ValueError('漏检帧不能包含预测位置')
            if row['projection_valid'] and (not frame['mapping']['valid'] or any(
                    type(row[k]) not in (int, float) or not math.isfinite(row[k])
                    or not 0 <= row[k] <= 100 for k in ('x_norm', 'y_norm'))):
                raise ValueError('足球地面投影标记或坐标无效')
            keys = ('frame_index', 'timestamp_s', 'detected', 'image_x', 'image_y', 'bbox_xyxy',
                    'confidence', 'segment_id', 'tracking_status', 'x_norm', 'y_norm',
                    'projection_valid', 'projection_reason')
            clean = {key: row[key] for key in keys}
            for key in ('x_norm', 'y_norm'):
                value = clean[key]
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                    raise ValueError('投影坐标含非有限数值')
            clean['grounded_verified'] = False
            frames.append(clean)
        return {'available': True, 'frames': frames, 'image_size': meta['image_size'], 'note': NOTE,
                'summary': {'frames': len(frames), 'detected_frames': sum(r['detected'] for r in frames),
                            'projected_frames': sum(r['projection_valid'] for r in frames)}}
    except (ValueError, KeyError, TypeError, OSError) as error:
        reason = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else '足球结果格式或文件读取失败'
        return dict(missing, reason=reason)
