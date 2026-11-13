"""复用关键点与球员观测，比较映射参数；不运行检测或球队模型。"""

import argparse
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

from sports.common.analysis import MappingSettings, fit_mapping, map_position
from sports.configs.soccer import SoccerPitchConfiguration


def compare_settings(data, thresholds):
    """结果是几何一致性与可用量，不是人工标注的定位准确率。"""
    if data.get('schema_version') != '1.0':
        raise ValueError('不支持的数据格式版本')
    if any('keypoints' not in frame for frame in data['frames']):
        raise ValueError('此结果未保存关键点，需使用新版分析命令重新处理一次')
    config = SoccerPitchConfiguration(**data['metadata']['template_cm'])
    base = MappingSettings(**data['metadata']['mapping_settings'])
    results = []
    for threshold in thresholds:
        settings = replace(base, ransac_pixels=threshold)
        reasons, errors, jumps = Counter(), [], []
        valid_observations = total_observations = out_of_bounds = 0
        previous = {}
        rejected = []
        for frame in data['frames']:
            raw = frame['keypoints']
            if raw is None:
                matrix, quality = None, {'valid': False, 'reason': 'missing_keypoints'}
            else:
                matrix, quality = fit_mapping(raw['xy'], raw['confidence'], config, settings)
            reasons[quality['reason']] += 1
            if quality['valid']:
                errors.append(quality['reprojection_error_px'])
            else:
                rejected.append(frame['frame_index'])
            for row in frame['positions']:
                total_observations += 1
                x, y, valid, reason = map_position([row['image_x'], row['image_y']], matrix, config)
                out_of_bounds += reason == 'out_of_bounds'
                if valid:
                    valid_observations += 1
                    last = previous.get(row['track_id'])
                    if last and frame['frame_index'] == last[0] + 1:
                        jumps.append(float(np.hypot(x - last[1], y - last[2])))
                    previous[row['track_id']] = (frame['frame_index'], x, y)
        results.append({
            'ransac_pixels': threshold, 'frame_reasons': dict(reasons),
            'valid_observations': valid_observations,
            'total_observations': total_observations, 'out_of_bounds': out_of_bounds,
            'accepted_frame_inlier_error_median_px': float(np.median(errors)) if errors else None,
            'accepted_frame_inlier_error_p95_px': float(np.percentile(errors, 95)) if errors else None,
            'consecutive_observation_delta_median_norm': float(np.median(jumps)) if jumps else None,
            'consecutive_observation_delta_p95_norm': float(np.percentile(jumps, 95)) if jumps else None,
            'consecutive_observation_delta_max_norm': max(jumps) if jumps else None,
            'rejected_frame_indices': rejected,
        })
    return {'source_video': data['metadata']['source_video'],
            'source_analysis_status': data['summary']['status'],
            'frame_count': len(data['frames']),
            'note': '复用同一份观测；误差来自拟合内点，不是独立真值误差。帧间变化含真实运动和映射误差，不等于速度。',
            'results': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='离线比较球场映射参数')
    parser.add_argument('--input', required=True, help='保存了原始关键点的 analysis.json')
    parser.add_argument('--output', required=True, help='比较结果 JSON')
    parser.add_argument('--thresholds', nargs='+', type=float, default=[8., 16.])
    args = parser.parse_args()
    with open(args.input, encoding='utf-8') as stream:
        data = json.load(stream)
    result = compare_settings(data, args.thresholds)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
    print(f'参数比较已保存：{output.resolve()}')
