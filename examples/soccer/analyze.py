"""处理一次视频，导出球员与守门员的相对站位数据。"""

import argparse
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import supervision as sv
from ultralytics import YOLO

from examples.soccer.main import (
    PLAYER_CLASS_ID, GOALKEEPER_CLASS_ID, PLAYER_DETECTION_MODEL_PATH,
    PITCH_DETECTION_MODEL_PATH, get_crops, resolve_device,
)
from sports.common.analysis import (
    AnalysisWriter, MappingSettings, fit_mapping, load_pitch_profile,
    map_position, settings_metadata,
)
from sports.common.team import TeamClassifier


def analyze(source, output_dir, device='auto', pitch_profile=None,
            max_frames=None, save_video=False, settings=None):
    """球队编号仅在本次分析中有效，跟踪编号不等于球衣号码。"""
    settings = settings or MappingSettings()
    if max_frames is not None and max_frames <= 0:
        raise ValueError('处理帧数必须大于 0')
    info = sv.VideoInfo.from_video_path(source)
    if info.fps <= 0:
        raise ValueError('视频帧率无效，无法确定时间戳')
    if max_frames is not None:
        total = min(max_frames, info.total_frames)
    else:
        total = info.total_frames
    if total <= 0:
        raise ValueError('视频没有可处理帧，请检查视频文件')
    profile, config = load_pitch_profile(pitch_profile)
    device = resolve_device(device)
    metadata = {
        'source_video': str(Path(source).resolve()), 'fps': info.fps,
        'source_total_frames': info.total_frames, 'requested_frames': total,
        'device': device, 'pitch_profile': profile,
        'mapping_settings': settings_metadata(settings),
        'template_cm': {'length': config.length, 'width': config.width,
                        'penalty_box_length': config.penalty_box_length,
                        'penalty_box_width': config.penalty_box_width},
        'coordinate_system': '球场模板左上角为原点，x 沿长度、y 沿宽度，范围 0～100',
        'coordinate_basis': 'relative_template' if profile['status'] == 'unknown' else profile['status'],
        'timestamp_basis': 'frame_index / fps；不是转播比分牌时间，变帧率视频需预先转换',
        'identity_note': '跟踪编号仅在本次视频中有效；球队 0/1 不代表主客队；镜头切换可能导致身份变化',
        'quality_note': '有效仅表示通过几何检查，不表示已测得真实位置误差；未使用历史矩阵补帧',
        'models': {'player': PLAYER_DETECTION_MODEL_PATH, 'pitch': PITCH_DETECTION_MODEL_PATH},
    }
    writer = AnalysisWriter(output_dir, metadata)
    status = 'error'
    try:
        player_model = YOLO(PLAYER_DETECTION_MODEL_PATH).to(device)
        pitch_model = YOLO(PITCH_DETECTION_MODEL_PATH).to(device)
        crops = []
        stride = max(1, min(60, total // 10))
        for index, frame in enumerate(sv.get_video_frames_generator(source_path=source, stride=stride)):
            if index * stride >= total:
                break
            result = player_model(frame, imgsz=1280, verbose=False)[0]
            detected = sv.Detections.from_ultralytics(result)
            crops.extend(get_crops(frame, detected[detected.class_id == PLAYER_CLASS_ID]))
        if len(crops) < 16:
            raise ValueError('可用球员样本不足，无法区分球队，请使用更长的正常比赛片段')
        classifier = TeamClassifier(device=device)
        classifier.fit(crops)
        tracker = sv.ByteTrack(frame_rate=round(info.fps), minimum_consecutive_frames=3)
        sink = sv.VideoSink(str(Path(output_dir) / 'observations.mp4'), info) if save_video else nullcontext()
        box = sv.BoxAnnotator()
        label = sv.LabelAnnotator()
        with sink as video:
            for index, frame in enumerate(sv.get_video_frames_generator(source_path=source)):
                if index >= total:
                    break
                timestamp = index / info.fps
                pitch_result = pitch_model(frame, verbose=False)[0]
                keypoints = sv.KeyPoints.from_ultralytics(pitch_result)
                if len(keypoints.xy) and keypoints.keypoint_confidence is not None:
                    matrix, quality = fit_mapping(keypoints.xy[0], keypoints.keypoint_confidence[0], config, settings)
                else:
                    matrix, quality = None, {'valid': False, 'reason': 'missing_keypoints'}
                detected = sv.Detections.from_ultralytics(player_model(frame, imgsz=1280, verbose=False)[0])
                # 裁判和足球均不进入本轮轨迹数据与跟踪关联。
                detected = detected[np.isin(detected.class_id, [PLAYER_CLASS_ID, GOALKEEPER_CLASS_ID])]
                detected = tracker.update_with_detections(detected)
                players_mask = detected.class_id == PLAYER_CLASS_ID
                teams = np.full(len(detected), -1, dtype=int)
                teams[players_mask] = classifier.predict(get_crops(frame, detected[players_mask]))
                anchors = detected.get_anchors_coordinates(sv.Position.BOTTOM_CENTER)
                centroids = [anchors[players_mask & (teams == team)].mean(axis=0)
                             if np.any(players_mask & (teams == team)) else None for team in (0, 1)]
                if all(c is not None for c in centroids):
                    for i in np.flatnonzero(~players_mask):
                        teams[i] = int(np.argmin([np.linalg.norm(anchors[i] - c) for c in centroids]))
                records = []
                for i, anchor in enumerate(anchors):
                    x, y, valid, reason = map_position(anchor, matrix, config)
                    role = 'player' if players_mask[i] else 'goalkeeper'
                    records.append({
                        'frame_index': index, 'timestamp_s': timestamp,
                        'track_id': int(detected.tracker_id[i]), 'role': role,
                        'team_id': int(teams[i]) if teams[i] >= 0 else None,
                        'team_assignment': ('appearance_cluster' if players_mask[i] else
                                            'proximity_estimate' if teams[i] >= 0 else 'unknown'),
                        'detection_confidence': float(detected.confidence[i]),
                        'image_x': float(anchor[0]), 'image_y': float(anchor[1]),
                        'x_norm': x, 'y_norm': y, 'coordinate_valid': valid,
                        'invalid_reason': reason,
                    })
                writer.add_frame(index, timestamp, quality, records)
                if save_video:
                    annotated = box.annotate(frame.copy(), detected)
                    labels = [f"ID {r['track_id']} T{r['team_id']} {'OK' if r['coordinate_valid'] else 'INVALID'}"
                              for r in records]
                    video.write_frame(label.annotate(annotated, detected, labels))
                if (index + 1) % 25 == 0:
                    print(f'已导出 {index + 1}/{total} 帧', flush=True)
        processed = len(writer.frames)
        status = 'complete' if processed == total else 'incomplete'
    finally:
        writer.close(status)
    print(f'数据已保存：{Path(output_dir).resolve()}，状态：{status}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='导出带有效性标记的足球站位数据')
    parser.add_argument('--source', required=True, help='输入视频路径')
    parser.add_argument('--output-dir', required=True, help='新的结果目录')
    parser.add_argument('--device', default='auto', choices=['auto', 'mps', 'cpu', 'cuda'])
    parser.add_argument('--pitch-profile', help='可选的球场尺寸及来源 JSON')
    parser.add_argument('--max-frames', type=int, help='短片验证使用的最大帧数')
    parser.add_argument('--save-video', action='store_true', help='同时保存含跟踪编号和有效性状态的视频')
    parser.add_argument('--keypoint-confidence', type=float, default=0.5)
    parser.add_argument('--min-inliers', type=int, default=6)
    parser.add_argument('--ransac-pixels', type=float, default=8.0)
    parser.add_argument('--min-inlier-ratio', type=float, default=0.6)
    args = parser.parse_args()
    analyze(args.source, args.output_dir, args.device, args.pitch_profile,
            args.max_frames, args.save_video,
            MappingSettings(args.keypoint_confidence, args.min_inliers,
                            args.ransac_pixels, args.min_inlier_ratio))
