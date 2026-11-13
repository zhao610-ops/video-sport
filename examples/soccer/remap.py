"""复用已有关键点和球员观测，重新映射坐标，不重新识别视频。"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from sports.common.analysis import (
    AnalysisWriter, MappingSettings, fit_mapping, load_pitch_profile,
    map_position, settings_metadata,
)
from sports.configs.soccer import SoccerPitchConfiguration


def remap(input_path, output_dir, pitch_profile=None, anchor_policy=None,
          require_region_support=False):
    with open(input_path, encoding='utf-8') as stream:
        data = json.load(stream)
    if data.get('schema_version') != '1.0' or any('keypoints' not in f for f in data['frames']):
        raise ValueError('需要包含原始关键点的 1.0 版分析结果')
    metadata = dict(data['metadata'])
    settings = MappingSettings(**metadata['mapping_settings'])
    if anchor_policy is not None:
        settings = replace(settings, anchor_policy=anchor_policy)
    if require_region_support:
        settings = replace(settings, require_region_support=True)
    if pitch_profile:
        profile, config = load_pitch_profile(pitch_profile)
        metadata['pitch_profile'] = profile
        metadata['template_cm'] = {'length': config.length, 'width': config.width,
                                   'penalty_box_length': config.penalty_box_length,
                                   'penalty_box_width': config.penalty_box_width}
        metadata['coordinate_basis'] = profile['status']
    else:
        config = SoccerPitchConfiguration(**metadata['template_cm'])
    metadata['mapping_settings'] = settings_metadata(settings)
    metadata['remapped_from'] = str(Path(input_path).resolve())
    metadata['remap_note'] = '仅重算映射；时间、检测脚点、跟踪编号和球队保留原记录，参考尺寸不视为历史真值'
    writer = AnalysisWriter(output_dir, metadata)
    status = 'error'
    try:
        for frame in data['frames']:
            raw = frame['keypoints']
            if raw is None:
                matrix, quality = None, {'valid': False, 'reason': 'missing_keypoints'}
            else:
                matrix, quality = fit_mapping(raw['xy'], raw['confidence'], config, settings)
            records = []
            for row in frame['positions']:
                x, y, valid, reason = map_position([row['image_x'], row['image_y']], matrix, config)
                records.append(dict(row, x_norm=x, y_norm=y,
                                    coordinate_valid=valid, invalid_reason=reason))
            writer.add_frame(frame['frame_index'], frame['timestamp_s'], quality, records, raw)
        status = data['summary']['status']
    finally:
        writer.close(status)
    print(f'坐标重算已完成：{Path(output_dir).resolve()}，状态：{status}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='不运行识别模型，重算并导出相对坐标')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--pitch-profile', help='带来源和状态的可选参考尺寸文件')
    parser.add_argument('--anchor-policy', choices=['all', 'structural'])
    parser.add_argument('--require-region-support', action='store_true')
    args = parser.parse_args()
    remap(args.input, args.output_dir, args.pitch_profile,
          args.anchor_policy, args.require_region_support)
