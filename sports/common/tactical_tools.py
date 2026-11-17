"""供智能体调用的确定性指标工具，只返回经过筛选的统计数据。"""

import math
import statistics
from collections import Counter

from sports.common.tactics import METRIC_DEFINITIONS
from sports.common.tactical_knowledge import TacticalKnowledgeBase


METRICS = ('center_x', 'center_y', 'width', 'longitudinal_span')


class TacticalTools:
    def __init__(self, dataset):
        if dataset.get('schema_version') != 'tactics-1.0' or not dataset.get('team_frames'):
            raise ValueError('需要非空的 tactics-1.0 指标文件')
        self.dataset = dataset
        self.knowledge = TacticalKnowledgeBase()
        self.rows = dataset['team_frames']
        times = sorted({row['timestamp_s'] for row in self.rows})
        if not all(isinstance(t, (int, float)) and math.isfinite(t) and t >= 0 for t in times):
            raise ValueError('指标时间戳无效')
        self.start = times[0]
        self.step = statistics.median(b-a for a, b in zip(times, times[1:])) if len(times) > 1 else None
        self.end = round(times[-1] + (self.step or .000001), 9)
        for row in self.rows:
            if type(row['team_id']) is not int or row['team_id'] not in (0, 1):
                raise ValueError('指标球队编号无效')
            if row['available'] and any(
                isinstance(row[k], bool) or not isinstance(row[k], (float, int))
                or not math.isfinite(row[k]) or not 0 <= row[k] <= 100 for k in METRICS
            ):
                raise ValueError('有效指标包含不合理数值')

    def overview(self):
        metadata = self.dataset['metadata']
        # 不返回本机文件路径、完整逐帧数据、视频或配置中的凭据。
        return {
            'observed_interval_s': [self.start, self.end],
            'interval_convention': '左闭右开 [start_s, end_s)；末端按时间戳步长估计',
            'frame_count': self.dataset['summary']['frame_count'],
            'source_analysis_status': metadata['source_analysis_status'],
            'include_goalkeepers': metadata['include_goalkeepers'],
            'min_players': metadata['min_players'],
            'pitch_dimension_status': metadata['pitch_profile']['status'],
            'metric_definitions': METRIC_DEFINITIONS,
            'limitations': ['只统计可见且有效的目标，不能代表全场阵型',
                            '球队 0/1 不代表主客队，x 方向不代表进攻方向',
                            '坐标为百分比，不支持米制距离、速度、球权或比赛胜负预测',
                            '镜头覆盖、误检、跟踪和球队误分可能影响指标，缺失数据未插值'],
        }

    @staticmethod
    def _number(value):
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError('时间参数必须是有限的非负数字')
        return float(value)

    def summarize(self, team_id, start_s=None, end_s=None):
        if type(team_id) is not int or team_id not in (0, 1):
            raise ValueError('球队编号必须为 0 或 1')
        start = self.start if start_s is None else self._number(start_s)
        end = self.end if end_s is None else self._number(end_s)
        if end <= start:
            raise ValueError('时间段结束时间必须大于开始时间')
        selected = [r for r in self.rows if r['team_id'] == team_id and start <= r['timestamp_s'] < end]
        valid = [r for r in selected if r['available']]
        result = {
            'team_id': team_id, 'requested_interval_s': [start, end],
            'extends_beyond_dataset': start < self.start or end > self.end + .000001,
            'selected_frames': len(selected), 'available_frames': len(valid),
            'available_ratio': len(valid) / len(selected) if selected else None,
            'missing_reasons': dict(Counter(r['reason'] for r in selected if not r['available'])),
            'statistics': {}, 'time_bins': [],
            'averaging': '对可用帧等权平均；缺失不作零，不作连续趋势或因果推断',
        }
        for metric in METRICS:
            values = [r[metric] for r in valid]
            result['statistics'][metric] = {
                'mean': statistics.mean(values) if values else None,
                'min': min(values) if values else None, 'max': max(values) if values else None,
                'first': values[0] if values else None, 'last': values[-1] if values else None,
            }
        result['first_available_time_s'] = valid[0]['timestamp_s'] if valid else None
        result['last_available_time_s'] = valid[-1]['timestamp_s'] if valid else None
        result['valid_player_count_range'] = [min(r['visible_count'] for r in valid),
                                              max(r['visible_count'] for r in valid)] if valid else None
        widest = max(valid, key=lambda r: r['width']) if valid else None
        result['widest_observation'] = ({k: widest[k] for k in ('frame_index', 'timestamp_s', 'width', 'visible_count')}
                                         if widest else None)
        if selected:
            # 最多约 60 个时间桶，避免把长视频的全部逐帧数据传给模型。
            bin_size = max(1, math.ceil((end-start) / 60))
            bins = {}
            for row in selected:
                index = int((row['timestamp_s'] - start) // bin_size)
                bins.setdefault(index, []).append(row)
            for index, group in sorted(bins.items()):
                usable = [row for row in group if row['available']]
                result['time_bins'].append({
                    'interval_s': [start + index*bin_size, min(end, start + (index+1)*bin_size)],
                    'selected_frames': len(group), 'available_frames': len(usable),
                    'means': {metric: statistics.mean(r[metric] for r in usable) if usable else None
                              for metric in METRICS},
                })
        return result

    def compare(self, team_id, a_start_s, a_end_s, b_start_s, b_end_s):
        a_start_s, a_end_s, b_start_s, b_end_s = (
            self._number(v) for v in (a_start_s, a_end_s, b_start_s, b_end_s))
        a = self.summarize(team_id, a_start_s, a_end_s)
        b = self.summarize(team_id, b_start_s, b_end_s)
        differences = {}
        for metric in METRICS:
            x, y = a['statistics'][metric]['mean'], b['statistics'][metric]['mean']
            differences[metric] = y-x if x is not None and y is not None else None
        return {'team_id': team_id, 'window_a': a, 'window_b': b,
                'mean_difference_b_minus_a': differences,
                'difference_unit': '百分点；中心 x/纵向跨度参照长度，中心 y/宽度参照宽度',
                'windows_overlap': max(a_start_s, b_start_s) < min(a_end_s, b_end_s),
                'limitation': '差值受可见人数、镜头覆盖和数据质量影响，不自动代表战术变化'}

    def execute(self, name, arguments):
        allowed = {
            'search_tactical_knowledge': ({'query', 'limit'}, {'query'}, self.knowledge.search),
            'get_dataset_overview': (set(), set(), self.overview),
            'summarize_team': ({'team_id', 'start_s', 'end_s'}, {'team_id'}, self.summarize),
            'compare_windows': ({'team_id', 'a_start_s', 'a_end_s', 'b_start_s', 'b_end_s'},
                                {'team_id', 'a_start_s', 'a_end_s', 'b_start_s', 'b_end_s'}, self.compare),
        }
        if name not in allowed or not isinstance(arguments, dict):
            raise ValueError('不支持的工具或参数格式')
        keys, required, function = allowed[name]
        if set(arguments) - keys or not required.issubset(arguments):
            raise ValueError('工具参数缺失或包含未允许字段')
        return function(**arguments)


def tool_definitions():
    functions = [
        ('search_tactical_knowledge', '检索中文足球战术概念、判断需要的数据和来源；不证明本场比赛发生了该战术',
         {'query': {'type': 'string', 'minLength': 1, 'maxLength': 500},
          'limit': {'type': 'integer', 'minimum': 1, 'maximum': 5}}, ['query']),
        ('get_dataset_overview', '首先查看可查询时间范围、统计口径、单位和数据限制', {}, []),
        ('summarize_team', '查询某队时间段内的中心、宽度、纵向跨度、可用帧及时间分桶',
         {'team_id': {'type': 'integer', 'enum': [0, 1]},
          'start_s': {'type': 'number', 'minimum': 0}, 'end_s': {'type': 'number', 'minimum': 0}}, ['team_id']),
        ('compare_windows', '比较同一球队两个明确时间段的均值与可用数据，返回后段减前段的差值',
         {'team_id': {'type': 'integer', 'enum': [0, 1]},
          **{key: {'type': 'number', 'minimum': 0}
             for key in ('a_start_s', 'a_end_s', 'b_start_s', 'b_end_s')}},
         ['team_id', 'a_start_s', 'a_end_s', 'b_start_s', 'b_end_s']),
    ]
    return [{'type': 'function', 'function': {'name': name, 'description': description,
             'parameters': {'type': 'object', 'properties': properties,
                            'required': required, 'additionalProperties': False}}}
            for name, description, properties, required in functions]
