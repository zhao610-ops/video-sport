"""从保存的站位计算可见球员指标，不推断画面外的完整阵型。"""

import math
from collections import Counter


METRIC_DEFINITIONS = {
    'center_x': '有效可见球员 x 坐标的算术平均，单位为球场长度百分比',
    'center_y': '有效可见球员 y 坐标的算术平均，单位为球场宽度百分比',
    'width': '有效可见球员 max(y)-min(y)，单位为球场宽度百分比',
    'longitudinal_span': '有效可见球员 max(x)-min(x)，单位为球场长度百分比；不代表进攻方向',
}


def calculate_tactics(analysis, include_goalkeepers, min_players=2):
    """至少两名不同跟踪目标才输出中心和跨度，始终保留人数及缺失原因。"""
    if analysis.get('schema_version') != '1.0':
        raise ValueError('不支持的站位数据版本')
    if not isinstance(include_goalkeepers, bool):
        raise ValueError('必须明确是否包含守门员')
    if isinstance(min_players, bool) or not isinstance(min_players, int) or min_players < 2:
        raise ValueError('计算跨度至少需要两名球员')
    rows = []
    exclusions = Counter()
    max_players = 11 if include_goalkeepers else 10
    if min_players > max_players:
        raise ValueError('最低人数不能超过当前角色范围的球队人数上限')
    last_index = last_time = -1
    for frame in analysis['frames']:
        index, timestamp = frame['frame_index'], frame['timestamp_s']
        if index <= last_index or not math.isfinite(timestamp) or timestamp < 0 or timestamp <= last_time:
            raise ValueError('帧编号及时间戳必须严格递增且有效')
        last_index, last_time = index, timestamp
        mapping_valid = frame['mapping']['valid'] is True
        eligible = []
        for position in frame['positions']:
            reason = None
            role = position['role']
            if role not in ('player', 'goalkeeper'):
                reason = 'unsupported_role'
            elif role == 'goalkeeper' and not include_goalkeepers:
                reason = 'goalkeeper_excluded'
            elif not mapping_valid:
                reason = 'frame_mapping_invalid'
            elif position['coordinate_valid'] is not True:
                reason = 'coordinate_invalid'
            elif type(position['team_id']) is not int or position['team_id'] not in (0, 1):
                reason = 'unknown_team'
            elif type(position['track_id']) is not int:
                reason = 'missing_track_id'
            else:
                x, y = position['x_norm'], position['y_norm']
                if any(isinstance(v, bool) or not isinstance(v, (float, int))
                       or not math.isfinite(v) or not 0 <= v <= 100 for v in (x, y)):
                    reason = 'invalid_coordinate_value'
            if reason:
                exclusions[reason] += 1
            else:
                eligible.append(position)
        identifiers = Counter(position['track_id'] for position in eligible)
        unique = [position for position in eligible if identifiers[position['track_id']] == 1]
        exclusions['duplicate_track_id'] += len(eligible) - len(unique)
        for team in (0, 1):
            players = [position for position in unique if position['team_id'] == team]
            goalkeeper_count = sum(position['role'] == 'goalkeeper' for position in players)
            exceeds_limit = len(players) > max_players or len(players) - goalkeeper_count > 10 or goalkeeper_count > 1
            available = mapping_valid and len(players) >= min_players and not exceeds_limit
            row = {
                'frame_index': index, 'timestamp_s': timestamp, 'team_id': team,
                'visible_count': len(players),
                'goalkeeper_count': goalkeeper_count,
                'available': available,
                'reason': ('ok' if available else 'frame_mapping_invalid' if not mapping_valid
                           else 'player_count_exceeds_limit' if exceeds_limit else 'insufficient_players'),
                'center_x': None, 'center_y': None, 'width': None, 'longitudinal_span': None,
                'min_x': None, 'max_x': None, 'min_y': None, 'max_y': None,
                'track_ids': sorted(position['track_id'] for position in players),
            }
            if available:
                xs = [position['x_norm'] for position in players]
                ys = [position['y_norm'] for position in players]
                row.update(center_x=sum(xs)/len(xs), center_y=sum(ys)/len(ys),
                           width=max(ys)-min(ys), longitudinal_span=max(xs)-min(xs),
                           min_x=min(xs), max_x=max(xs), min_y=min(ys), max_y=max(ys))
            rows.append(row)
    metadata = analysis['metadata']
    return {
        'schema_version': 'tactics-1.0',
        'metadata': {
            'source_video': metadata['source_video'],
            'source_analysis_status': analysis['summary']['status'],
            'pitch_profile': metadata['pitch_profile'],
            'template_cm': metadata['template_cm'],
            'include_goalkeepers': include_goalkeepers, 'min_players': min_players,
            'max_players': max_players,
            'metric_definitions': METRIC_DEFINITIONS,
            'note': '仅描述可见有效球员；至少两人是计算门槛，不是完整阵型的可靠性标准。'
                    '镜头覆盖、漏检和球队误分会影响指标；两队编号不是主客队。'
                    '不插值、不平滑、不计算米制距离、速度或自动判断进攻方向。',
        },
        'summary': {
            'frame_count': len(analysis['frames']), 'team_frame_count': len(rows),
            'available_team_frames': sum(row['available'] for row in rows),
            'missing_reasons': dict(Counter(row['reason'] for row in rows if not row['available'])),
            'excluded_observations': {k: v for k, v in exclusions.items() if v},
        },
        'team_frames': rows,
    }
