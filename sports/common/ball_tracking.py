"""单足球的图像平面关联；不插值、不把预测位置当作检测结果。"""

import math


class ObservedBallTracker:
    def __init__(self, width, height, min_confidence=.25, max_gap=5, gate_fraction=.06):
        if width <= 0 or height <= 0 or not 0 < min_confidence <= 1 or max_gap < 1:
            raise ValueError('足球跟踪参数无效')
        self.width, self.height = width, height
        self.diagonal = math.hypot(width, height)
        self.min_confidence, self.max_gap, self.gate_fraction = min_confidence, max_gap, gate_fraction
        self.previous = None
        self.older = None
        self.segment = 0
        self.last_index = -1

    def update(self, frame_index, candidates, scene_changed=False):
        if frame_index <= self.last_index:
            raise ValueError('足球观测帧编号必须严格递增')
        self.last_index = frame_index
        if scene_changed:
            self.previous = None
            self.older = None
        usable = []
        for candidate in candidates:
            box, confidence = candidate.get('bbox_xyxy'), candidate.get('confidence')
            if (not isinstance(box, (tuple, list)) or len(box) != 4
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
                    or type(confidence) not in (int, float) or not math.isfinite(confidence)
                    or not self.min_confidence <= confidence <= 1):
                continue
            x1, y1, x2, y2 = box
            if not 0 <= x1 < x2 <= self.width or not 0 <= y1 < y2 <= self.height:
                continue
            usable.append({'bbox_xyxy': list(box), 'confidence': confidence,
                           'image_x': (x1+x2)/2, 'image_y': (y1+y2)/2})
        missing = {'detected': False, 'image_x': None, 'image_y': None,
                   'bbox_xyxy': None, 'confidence': None, 'segment_id': None}
        if not usable:
            return dict(missing, tracking_status='not_detected')
        gap = frame_index-self.previous['frame_index'] if self.previous else None
        reset = self.previous is None or scene_changed or gap > self.max_gap
        if reset:
            chosen = max(usable, key=lambda c: c['confidence'])
        else:
            predicted = [self.previous['image_x'], self.previous['image_y']]
            if self.older and self.previous['frame_index']-self.older['frame_index'] == 1:
                for i, key in enumerate(('image_x', 'image_y')):
                    predicted[i] += (self.previous[key]-self.older[key])*min(gap, 2)
            chosen = min(usable, key=lambda c: math.hypot(c['image_x']-predicted[0], c['image_y']-predicted[1]))
            if math.hypot(chosen['image_x']-predicted[0], chosen['image_y']-predicted[1]) > self.diagonal*self.gate_fraction*gap:
                return dict(missing, tracking_status='association_rejected')
        if reset or gap != 1:
            self.segment += 1
            self.older = None
        else:
            self.older = self.previous
        self.previous = dict(chosen, frame_index=frame_index)
        return dict(chosen, detected=True, segment_id=self.segment,
                    tracking_status='initialized' if self.segment == 1 and reset else
                    'reacquired' if reset or gap != 1 else 'associated')


def tile_origins(length, tile=640, overlap=128):
    if length <= 0 or tile <= 0 or not 0 <= overlap < tile:
        raise ValueError('切片尺寸无效')
    if length <= tile:
        return [0]
    return sorted(set([*range(0, length-tile+1, tile-overlap), length-tile]))


def suppress_duplicates(candidates, threshold=.1):
    """按置信度做全图非极大值抑制，合并重叠切片的重复球框。"""
    selected = []
    for candidate in sorted(candidates, key=lambda c: c['confidence'], reverse=True):
        a = candidate['bbox_xyxy']
        keep = True
        for other in selected:
            b = other['bbox_xyxy']
            intersection = max(0, min(a[2], b[2])-max(a[0], b[0]))*max(0, min(a[3], b[3])-max(a[1], b[1]))
            union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
            if union > 0 and intersection/union > threshold:
                keep = False
                break
        if keep:
            selected.append(candidate)
    return selected
