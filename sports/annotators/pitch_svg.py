"""按照分析时使用的同一份模板绘制球场标线，不修改球员坐标。"""

import math


def draw_pitch_svg(template=None, width=100., height=60.):
    geometry = dict(length=12000., width=7000., penalty_box_length=1650.,
                    penalty_box_width=4032., goal_box_length=550.,
                    goal_box_width=1832., centre_circle_radius=915.,
                    penalty_spot_distance=1100., goal_width=732., corner_radius=100.)
    geometry.update(template or {})
    length, field_width = geometry['length'], geometry['width']
    sx, sy = width / length, height / field_width
    mid = field_width / 2
    stroke = width / 300
    lines = []

    def rect(name, x, y, w, h):
        lines.append(f'<rect data-marking="{name}" x="{x*sx:.5f}" y="{y*sy:.5f}" '
                     f'width="{w*sx:.5f}" height="{h*sy:.5f}"/>')

    def ellipse(name, x, y, radius, filled=False):
        lines.append(f'<ellipse data-marking="{name}" cx="{x*sx:.5f}" cy="{y*sy:.5f}" '
                     f'rx="{radius*sx:.5f}" ry="{radius*sy:.5f}" '
                     f'fill="{"#526354" if filled else "none"}"/>')

    rect('boundary', 0, 0, length, field_width)
    lines.append(f'<path data-marking="halfway-line" d="M{width/2} 0V{height}"/>')
    ellipse('centre-circle', length / 2, mid, geometry['centre_circle_radius'])
    ellipse('centre-mark', length / 2, mid, 18., True)
    for name, depth, box_width in (
        ('penalty-area', geometry['penalty_box_length'], geometry['penalty_box_width']),
        ('goal-area', geometry['goal_box_length'], geometry['goal_box_width']),
    ):
        rect(name + '-left', 0, mid - box_width / 2, depth, box_width)
        rect(name + '-right', length - depth, mid - box_width / 2, depth, box_width)
    rect('goal-left', -200, mid - geometry['goal_width'] / 2, 200, geometry['goal_width'])
    rect('goal-right', length, mid - geometry['goal_width'] / 2, 200, geometry['goal_width'])
    spot = geometry['penalty_spot_distance']
    ellipse('penalty-mark-left', spot, mid, 18., True)
    ellipse('penalty-mark-right', length - spot, mid, 18., True)
    radius = geometry['centre_circle_radius']
    offset = geometry['penalty_box_length'] - spot
    if abs(offset) < radius:
        half_arc = math.sqrt(radius ** 2 - offset ** 2)
        left = geometry['penalty_box_length']
        right = length - left
        lines.append(f'<path data-marking="penalty-arc-left" d="M{left*sx:.5f} {(mid-half_arc)*sy:.5f} '
                     f'A{radius*sx:.5f} {radius*sy:.5f} 0 0 1 {left*sx:.5f} {(mid+half_arc)*sy:.5f}"/>')
        lines.append(f'<path data-marking="penalty-arc-right" d="M{right*sx:.5f} {(mid+half_arc)*sy:.5f} '
                     f'A{radius*sx:.5f} {radius*sy:.5f} 0 0 1 {right*sx:.5f} {(mid-half_arc)*sy:.5f}"/>')
    r = geometry['corner_radius']
    for name, start, end in (
        ('top-left', (0, r), (r, 0)),
        ('top-right', (length-r, 0), (length, r)),
        ('bottom-right', (length, field_width-r), (length-r, field_width)),
        ('bottom-left', (r, field_width), (0, field_width-r)),
    ):
        lines.append(f'<path data-marking="corner-{name}" d="M{start[0]*sx:.5f} {start[1]*sy:.5f} '
                     f'A{r*sx:.5f} {r*sy:.5f} 0 0 0 {end[0]*sx:.5f} {end[1]*sy:.5f}"/>')
    return (f'<rect width="{width}" height="{height}" fill="#e8f1e6"/>'
            f'<g fill="none" stroke="#526354" stroke-width="{stroke}" pointer-events="none">'
            + ''.join(lines) + '</g>')
