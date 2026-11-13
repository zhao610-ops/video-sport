"""球场映射质量检查与可复用的数据导出。"""

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from sports.configs.soccer import SoccerPitchConfiguration


@dataclass
class MappingSettings:
    """初始实验参数会随结果一起保存，方便复现与调整。"""

    keypoint_confidence: float = 0.5
    min_inliers: int = 6
    ransac_pixels: float = 8.0
    min_inlier_ratio: float = 0.6
    anchor_policy: str = 'all'
    require_region_support: bool = False

    def __post_init__(self):
        if not 0 < self.keypoint_confidence <= 1:
            raise ValueError('关键点置信度必须位于 (0, 1]')
        if self.min_inliers < 4 or self.ransac_pixels <= 0:
            raise ValueError('内点至少为 4 个，像素误差阈值必须大于 0')
        if not 0 < self.min_inlier_ratio <= 1:
            raise ValueError('内点比例必须位于 (0, 1]')
        if self.anchor_policy not in ('all', 'structural'):
            raise ValueError('关键点策略应为 all 或 structural')


def load_pitch_profile(path=None):
    """未知尺寸使用上游相对模板，不将模板长宽解释成实测尺寸。"""
    profile = {'status': 'unknown', 'length_m': None, 'width_m': None,
               'source_url': None, 'venue': None, 'valid_from': None,
               'valid_to': None, 'note': None}
    if path:
        with open(path, encoding='utf-8') as stream:
            profile.update(json.load(stream))
    if profile['status'] not in ('unknown', 'reference', 'verified'):
        raise ValueError('尺寸状态应为 unknown、reference 或 verified')
    if profile['status'] == 'unknown':
        if profile['length_m'] is not None or profile['width_m'] is not None:
            raise ValueError('未知尺寸时长宽必须为空；参考尺寸应使用 reference')
        profile['note'] = profile['note'] or '未提供真实尺寸，仅使用相对模板'
        config = SoccerPitchConfiguration()
    else:
        length, width = profile['length_m'], profile['width_m']
        if (isinstance(length, bool) or isinstance(width, bool)
                or not isinstance(length, (int, float))
                or not isinstance(width, (int, float))
                or not np.isfinite([length, width]).all()
                or not 90 <= length <= 120 or not 45 <= width <= 90
                or length <= width):
            raise ValueError('十一人制球场长宽不合理，请检查单位与尺寸口径')
        if not profile.get('source_url') and not profile.get('note'):
            raise ValueError('参考或已核实尺寸必须记录来源或人工填写说明')
        config = SoccerPitchConfiguration(length=length * 100, width=width * 100)
    # 修正新分析流程的禁区标线，单位为厘米；上游示例配置保持独立。
    config.penalty_box_length = 1650
    config.penalty_box_width = 4032
    return profile, config


def fit_mapping(xy, confidence, config, settings):
    """在图像像素空间进行 RANSAC；失败帧不沿用旧矩阵。"""
    quality = {'valid': False, 'reason': '', 'selected_keypoints': 0,
               'inliers': 0, 'inlier_ratio': 0.0, 'reprojection_error_px': None}
    source = np.asarray(xy, dtype=float).reshape(-1, 2)
    target = np.asarray(config.vertices, dtype=float)
    conf = np.asarray(confidence, dtype=float).reshape(-1)
    if source.shape != target.shape or len(conf) != len(source):
        quality['reason'] = 'missing_keypoints'
        return None, quality
    mask = (np.isfinite(source).all(axis=1) & np.isfinite(conf)
            & (conf >= settings.keypoint_confidence)
            & (source[:, 0] > 1) & (source[:, 1] > 1))
    if settings.anchor_policy == 'structural':
        # 排除禁区线上的虚拟延长线交点，以及中圈没有相交标线的两侧辅助点。
        # 模型数组从 0 开始；真实中线与中圈交点仍参与拟合。
        mask[[10, 11, 18, 19, 30, 31]] = False
    indices = np.flatnonzero(mask)
    source, target = source[mask], target[mask]
    quality['selected_keypoints'] = len(source)
    if len(source) < settings.min_inliers:
        quality['reason'] = 'insufficient_keypoints'
        return None, quality
    if (np.linalg.matrix_rank(source - source.mean(axis=0)) < 2
            or np.linalg.matrix_rank(target - target.mean(axis=0)) < 2):
        quality['reason'] = 'degenerate_keypoints'
        return None, quality
    try:
        # 目标为图像坐标，使 RANSAC 阈值具有明确的像素单位。
        inverse, inlier_mask = cv2.findHomography(
            target, source, cv2.RANSAC, settings.ransac_pixels)
        if inverse is None or inlier_mask is None or not np.isfinite(inverse).all():
            raise ValueError('无法建立映射')
        inliers = inlier_mask.ravel().astype(bool)
        quality['inliers'] = int(inliers.sum())
        quality['inlier_ratio'] = float(inliers.mean())
        quality['inlier_keypoint_indices'] = indices[inliers].tolist()
        regions = np.where(target[:, 0] <= config.length / 4, 'left',
                           np.where(target[:, 0] >= config.length * 3 / 4, 'right', 'midfield'))
        quality['region_support'] = {
            name: {'selected': int((regions == name).sum()),
                   'inliers': int(((regions == name) & inliers).sum())}
            for name in ('left', 'midfield', 'right')
        }
        if (quality['inliers'] < settings.min_inliers
                or quality['inlier_ratio'] < settings.min_inlier_ratio):
            quality['reason'] = 'insufficient_inliers'
            return None, quality
        if settings.require_region_support and any(
                group['selected'] >= 2 and group['inliers'] < 2
                for group in quality['region_support'].values()):
            quality['reason'] = 'insufficient_region_support'
            return None, quality
        predicted = cv2.perspectiveTransform(target[inliers].reshape(-1, 1, 2), inverse)
        error = float(np.median(np.linalg.norm(
            predicted.reshape(-1, 2) - source[inliers], axis=1)))
        quality['reprojection_error_px'] = error
        matrix = np.linalg.inv(inverse)
        if not np.isfinite(matrix).all() or error > settings.ransac_pixels:
            raise ValueError('映射不稳定')
    except (cv2.error, ValueError, np.linalg.LinAlgError):
        quality['reason'] = 'mapping_failed'
        return None, quality
    quality.update(valid=True, reason='ok')
    return matrix, quality


def map_position(pixel_xy, matrix, config):
    """保留越界值供排查，不裁剪、不插值，不把无穷值写入 JSON。"""
    if matrix is None:
        return None, None, False, 'frame_mapping_invalid'
    point = np.asarray([*pixel_xy, 1.0], dtype=float)
    projected = matrix @ point
    if not np.isfinite(projected).all() or abs(projected[2]) < 1e-9:
        return None, None, False, 'non_finite_coordinate'
    x, y = projected[:2] / projected[2] / [config.length, config.width] * 100
    if not np.isfinite([x, y]).all():
        return None, None, False, 'non_finite_coordinate'
    valid = bool(0 <= x <= 100 and 0 <= y <= 100)
    return float(x), float(y), valid, 'ok' if valid else 'out_of_bounds'


class AnalysisWriter:
    """逐帧写入 CSV，并在 JSON 中保存帧状态及元数据。"""

    fields = ['frame_index', 'timestamp_s', 'track_id', 'role', 'team_id',
              'team_assignment', 'detection_confidence', 'image_x', 'image_y',
              'x_norm', 'y_norm', 'coordinate_valid', 'invalid_reason']

    def __init__(self, directory, metadata):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        # 单次分析使用新目录，避免覆盖之前的实验或混合两个视频的数据。
        if any((self.directory / name).exists() for name in ('positions.csv', 'analysis.json')):
            raise FileExistsError('分析结果已存在，请指定新的输出目录')
        self.metadata = metadata
        self.frames = []
        self.rows = 0
        self.invalid = Counter()
        self.stream = open(self.directory / 'positions.csv', 'w', encoding='utf-8', newline='')
        self.writer = csv.DictWriter(self.stream, fieldnames=self.fields)
        self.writer.writeheader()

    def add_frame(self, index, timestamp, quality, records, keypoints=None):
        self.writer.writerows(records)
        self.stream.flush()
        self.rows += len(records)
        self.invalid.update(r['invalid_reason'] for r in records if not r['coordinate_valid'])
        self.frames.append({'frame_index': index, 'timestamp_s': timestamp,
                            'mapping': quality, 'positions': records,
                            'keypoints': keypoints})

    def close(self, status):
        self.stream.close()
        result = {'schema_version': '1.0', 'metadata': self.metadata,
                  'summary': {'status': status, 'frames': len(self.frames),
                              'observations': self.rows, 'invalid_reasons': dict(self.invalid)},
                  'frames': self.frames}
        temporary = self.directory / 'analysis.json.tmp'
        with open(temporary, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        temporary.replace(self.directory / 'analysis.json')


def settings_metadata(settings):
    return asdict(settings)
