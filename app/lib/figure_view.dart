import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'theme.dart';

class FigureView extends StatelessWidget {
  const FigureView({super.key, required this.figure, this.caption});

  final Map<String, dynamic> figure;
  final String? caption;

  @override
  Widget build(BuildContext context) {
    final type = (figure['type'] ?? 'number_line').toString();
    final height = switch (type) {
      'plane_geometry' || 'three_view' || 'net' => 260.0,
      'bar_chart' || 'histogram' || 'line_chart' || 'pie_chart' => 220.0,
      'angle' => 168.0,
      _ => 136.0,
    };
    final CustomPainter painter = switch (type) {
      'plane_geometry' => PlaneGeometryPainter(figure),
      'angle' => AnglePainter(figure),
      'bar_chart' || 'histogram' || 'line_chart' || 'pie_chart' => StatsPainter(figure),
      'three_view' || 'net' => GridFigurePainter(figure),
      _ => NumberLinePainter(figure),
    };

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
      decoration: BoxDecoration(
        color: AppColors.canvas,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.hairline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: height,
            width: double.infinity,
            child: ClipRect(
              child: CustomPaint(
                painter: painter,
              ),
            ),
          ),
          if (caption != null && caption!.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(caption!, style: AppType.caption),
          ],
        ],
      ),
    );
  }
}

int _gcd(int a, int b) {
  var x = a.abs();
  var y = b.abs();
  while (y != 0) {
    final next = x % y;
    x = y;
    y = next;
  }
  return x == 0 ? 1 : x;
}

String _fractionLabel(double value) {
  const denominators = [2, 3, 4, 5, 8];
  for (final den in denominators) {
    final scaled = value * den;
    if ((scaled - scaled.round()).abs() < 1e-6) {
      var num = scaled.round();
      final g = _gcd(num, den);
      num ~/= g;
      final bottom = den ~/ g;
      if (bottom == 1) return num.toString();
      final sign = num < 0 ? '−' : '';
      return '$sign${num.abs()}/$bottom';
    }
  }
  return value.toStringAsFixed(1);
}

class NumberLinePainter extends CustomPainter {
  NumberLinePainter(this.figure);

  final Map<String, dynamic> figure;

  @override
  void paint(Canvas canvas, Size size) {
    final minV = (figure['min'] as num).toDouble();
    final maxV = (figure['max'] as num).toDouble();
    final span = (maxV - minV).abs() < 0.001 ? 1.0 : maxV - minV;
    final left = 16.0;
    final right = size.width - 16;
    final y = size.height * 0.62;

    double xOf(double value) => left + (value - minV) / span * (right - left);

    final axis = Paint()
      ..color = AppColors.ink
      ..strokeWidth = 1.6
      ..style = PaintingStyle.stroke;
    canvas.drawLine(Offset(left, y), Offset(right, y), axis);
    final tip = Path()
      ..moveTo(right, y)
      ..lineTo(right - 8, y - 4)
      ..lineTo(right - 8, y + 4)
      ..close();
    canvas.drawPath(tip, Paint()..color = AppColors.ink);

    final highlight = figure['highlight'];
    if (highlight is Map) {
      final from = (highlight['from'] as num).toDouble();
      final to = (highlight['to'] as num).toDouble();
      canvas.drawLine(
        Offset(xOf(from), y),
        Offset(xOf(to), y),
        Paint()
          ..color = AppColors.primary
          ..strokeWidth = 4
          ..strokeCap = StrokeCap.round,
      );
    }

    final tick = Paint()
      ..color = AppColors.slate
      ..strokeWidth = 1.2;
    final label = TextPainter(textDirection: TextDirection.ltr);
    for (var value = minV.ceil(); value <= maxV.floor(); value++) {
      final x = xOf(value.toDouble());
      canvas.drawLine(Offset(x, y - 6), Offset(x, y + 6), tick);
      if (value % 1 == 0 && (maxV - minV) <= 16) {
        label.text = TextSpan(text: '$value', style: AppType.caption.copyWith(color: AppColors.slate));
        label.layout();
        label.paint(canvas, Offset(x - label.width / 2, y + 8));
      }
    }

    final points = figure['points'];
    if (points is List) {
      for (final raw in points) {
        if (raw is! Map) continue;
        final value = (raw['value'] as num).toDouble();
        final x = xOf(value);
        final ray = (raw['ray'] ?? '').toString();
        if (ray == 'left' || ray == 'right') {
          final endX = ray == 'left' ? left : right;
          canvas.drawLine(
            Offset(x, y),
            Offset(endX, y),
            Paint()
              ..color = AppColors.primary
              ..strokeWidth = 4
              ..strokeCap = StrokeCap.round,
          );
        }
        final fill = (raw['fill'] ?? 'closed').toString();
        final center = Offset(x, y);
        if (fill == 'open') {
          canvas.drawCircle(center, 5.5, Paint()..color = AppColors.canvas);
          canvas.drawCircle(
            center,
            5.5,
            Paint()
              ..color = AppColors.primary
              ..style = PaintingStyle.stroke
              ..strokeWidth = 2,
          );
        } else {
          canvas.drawCircle(center, 5, Paint()..color = AppColors.primary);
        }
        label.text = TextSpan(
          text: '${raw['label'] ?? ''}',
          style: AppType.caption.copyWith(color: AppColors.primary, fontWeight: FontWeight.w600),
        );
        label.layout();
        label.paint(canvas, Offset(x - label.width / 2, y - 28));
        if ((value - value.round()).abs() > 1e-6) {
          label.text = TextSpan(
            text: _fractionLabel(value),
            style: AppType.caption.copyWith(color: AppColors.primary, fontWeight: FontWeight.w600),
          );
          label.layout();
          label.paint(canvas, Offset(x - label.width / 2, y + 22));
        }
      }
    }
  }

  @override
  bool shouldRepaint(covariant NumberLinePainter oldDelegate) => oldDelegate.figure != figure;
}

class AnglePainter extends CustomPainter {
  AnglePainter(this.figure);

  final Map<String, dynamic> figure;

  @override
  void paint(Canvas canvas, Size size) {
    final degrees = (figure['degrees'] as num).toDouble().clamp(1, 179);
    final origin = Offset(size.width * 0.28, size.height * 0.78);
    final length = math.min(size.width, size.height) * 0.62;
    final rad = degrees * math.pi / 180;
    final endA = origin + Offset(length, 0);
    final endB = origin + Offset(length * math.cos(rad), -length * math.sin(rad));
    final ray = Paint()
      ..color = AppColors.ink
      ..strokeWidth = 1.8
      ..style = PaintingStyle.stroke;
    canvas.drawLine(origin, endA, ray);
    canvas.drawLine(origin, endB, ray);

    final arcRect = Rect.fromCircle(center: origin, radius: 36);
    canvas.drawArc(
      arcRect,
      0,
      -rad,
      false,
      Paint()
        ..color = AppColors.primary
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke,
    );

    final label = TextPainter(textDirection: TextDirection.ltr)
      ..text = TextSpan(
        text: '${figure['label'] ?? ''}',
        style: AppType.small.copyWith(color: AppColors.primary, fontWeight: FontWeight.w600),
      )
      ..layout();
    final mid = rad / 2;
    final labelAt = origin + Offset(52 * math.cos(mid), -52 * math.sin(mid));
    label.paint(canvas, labelAt);
  }

  @override
  bool shouldRepaint(covariant AnglePainter oldDelegate) => oldDelegate.figure != figure;
}

class PlaneGeometryPainter extends CustomPainter {
  PlaneGeometryPainter(this.figure);

  final Map<String, dynamic> figure;

  @override
  void paint(Canvas canvas, Size size) {
    final rawPts = (figure['points'] as List?) ?? const [];
    final rawLines = (figure['lines'] as List?) ?? const [];
    final rawCircles = (figure['circles'] as List?) ?? const [];
    final showAxes = figure['show_axes'] == true;

    final ptMap = <String, Offset>{};
    var minX = double.infinity;
    var maxX = -double.infinity;
    var minY = double.infinity;
    var maxY = -double.infinity;

    void includePt(double x, double y) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }

    for (final raw in rawPts) {
      if (raw is! Map) continue;
      final lbl = (raw['label'] ?? '').toString();
      final x = (raw['x'] as num?)?.toDouble() ?? 0.0;
      final y = (raw['y'] as num?)?.toDouble() ?? 0.0;
      if (lbl.isNotEmpty) {
        ptMap[lbl] = Offset(x, y);
        includePt(x, y);
      }
    }

    for (final raw in rawCircles) {
      if (raw is! Map) continue;
      final r = (raw['radius'] as num?)?.toDouble() ?? 1.0;
      final centerLbl = (raw['center'] ?? '').toString();
      final center = ptMap[centerLbl] ??
          Offset(
            (raw['x'] as num?)?.toDouble() ?? 0.0,
            (raw['y'] as num?)?.toDouble() ?? 0.0,
          );
      includePt(center.dx - r, center.dy - r);
      includePt(center.dx + r, center.dy + r);
    }

    if (showAxes) {
      includePt(0, 0);
    }

    if (!minX.isFinite || !maxX.isFinite) {
      minX = -5;
      maxX = 5;
      minY = -5;
      maxY = 5;
    }

    final spanX = math.max(maxX - minX, 2.0);
    final spanY = math.max(maxY - minY, 2.0);
    minX -= spanX * 0.24;
    maxX += spanX * 0.24;
    minY -= spanY * 0.24;
    maxY += spanY * 0.24;

    final padX = 28.0;
    final padY = 24.0;
    final usableW = math.max(size.width - padX * 2, 40.0);
    final usableH = math.max(size.height - padY * 2, 40.0);
    final scale = math.min(usableW / (maxX - minX), usableH / (maxY - minY));
    final cxWorld = (minX + maxX) / 2;
    final cyWorld = (minY + maxY) / 2;

    Offset toScreen(Offset w) {
      final sx = size.width / 2 + (w.dx - cxWorld) * scale;
      final sy = size.height / 2 - (w.dy - cyWorld) * scale;
      return Offset(sx, sy);
    }

    if (showAxes) {
      final origin = toScreen(Offset.zero);
      final axisPaint = Paint()
        ..color = AppColors.hairlineStrong
        ..strokeWidth = 1.2;
      canvas.drawLine(Offset(12, origin.dy), Offset(size.width - 12, origin.dy), axisPaint);
      canvas.drawLine(Offset(origin.dx, 12), Offset(origin.dx, size.height - 12), axisPaint);
    }

    for (final raw in rawCircles) {
      if (raw is! Map) continue;
      final r = (raw['radius'] as num?)?.toDouble() ?? 1.0;
      final centerLbl = (raw['center'] ?? '').toString();
      final centerW = ptMap[centerLbl] ??
          Offset(
            (raw['x'] as num?)?.toDouble() ?? 0.0,
            (raw['y'] as num?)?.toDouble() ?? 0.0,
          );
      final centerS = toScreen(centerW);
      canvas.drawCircle(
        centerS,
        r * scale,
        Paint()
          ..color = AppColors.primary
          ..strokeWidth = 1.8
          ..style = PaintingStyle.stroke,
      );
    }

    final tp = TextPainter(textDirection: TextDirection.ltr);

    for (final raw in rawLines) {
      if (raw is! Map) continue;
      final fromLbl = (raw['from'] ?? '').toString();
      final toLbl = (raw['to'] ?? '').toString();
      final w1 = ptMap[fromLbl];
      final w2 = ptMap[toLbl];
      if (w1 == null || w2 == null) continue;

      final p1 = toScreen(w1);
      final p2 = toScreen(w2);
      final kind = (raw['kind'] ?? 'segment').toString();
      final style = (raw['style'] ?? 'solid').toString();
      final label = (raw['label'] ?? '').toString();

      final dir = p2 - p1;
      final dist = dir.distance;
      if (dist < 1e-3) continue;
      final unit = dir / dist;
      final extendLen = 34.0;

      final startPt = kind == 'line' ? p1 - unit * extendLen : p1;
      final endPt = (kind == 'line' || kind == 'ray') ? p2 + unit * extendLen : p2;

      final linePaint = Paint()
        ..color = style == 'dashed' ? AppColors.primary : AppColors.ink
        ..strokeWidth = 2.0
        ..style = PaintingStyle.stroke;

      if (style == 'dashed') {
        _drawDashedLine(canvas, startPt, endPt, linePaint);
      } else {
        canvas.drawLine(startPt, endPt, linePaint);
      }

      final parallel = (raw['parallel'] as num?)?.toInt() ?? 0;
      if (parallel == 1 || parallel == 2) {
        _drawParallelMarks(canvas, (p1 + p2) / 2, unit, parallel, AppColors.primary);
      }

      if (label.isNotEmpty) {
        final mid = Offset((p1.dx + p2.dx) / 2, (p1.dy + p2.dy) / 2);
        final normal = Offset(-unit.dy, unit.dx);
        tp.text = TextSpan(
          text: label,
          style: AppType.caption.copyWith(color: AppColors.primary, fontWeight: FontWeight.w600),
        );
        tp.layout();
        tp.paint(canvas, mid + normal * 12 - Offset(tp.width / 2, tp.height / 2));
      }
    }

    for (final entry in ptMap.entries) {
      final s = toScreen(entry.value);
      canvas.drawCircle(s, 4.5, Paint()..color = AppColors.primary);
      tp.text = TextSpan(
        text: entry.key,
        style: AppType.small.copyWith(color: AppColors.ink, fontWeight: FontWeight.w600),
      );
      tp.layout();
      tp.paint(canvas, s + const Offset(6, -18));
    }

    final rawAngles = (figure['angles'] as List?) ?? const [];
    for (final raw in rawAngles) {
      if (raw is! Map) continue;
      final vertex = ptMap[(raw['vertex'] ?? '').toString()];
      final armFrom = ptMap[(raw['from'] ?? '').toString()];
      final armTo = ptMap[(raw['to'] ?? '').toString()];
      if (vertex == null || armFrom == null || armTo == null) continue;
      _drawMarkedAngle(
        canvas,
        tp,
        toScreen(vertex),
        toScreen(armFrom),
        toScreen(armTo),
        right: raw['right'] == true,
        label: (raw['label'] ?? '').toString(),
      );
    }

    if (figure['show_north'] == true) {
      _drawNorthArrow(canvas, size);
    }
  }

  void _drawDashedLine(Canvas canvas, Offset p1, Offset p2, Paint paint) {
    final total = (p2 - p1).distance;
    if (total <= 0) return;
    final dir = (p2 - p1) / total;
    var curr = 0.0;
    const dash = 6.0;
    const gap = 4.0;
    while (curr < total) {
      final end = math.min(curr + dash, total);
      canvas.drawLine(p1 + dir * curr, p1 + dir * end, paint);
      curr += dash + gap;
    }
  }

  @override
  bool shouldRepaint(covariant PlaneGeometryPainter oldDelegate) => oldDelegate.figure != figure;
}

void _drawNorthArrow(Canvas canvas, Size size) {
  final tip = Offset(size.width - 28, 14);
  final tail = Offset(size.width - 28, 48);
  final paint = Paint()
    ..color = AppColors.ink
    ..strokeWidth = 1.6
    ..style = PaintingStyle.stroke;
  canvas.drawLine(tail, tip, paint);
  final head = Path()
    ..moveTo(tip.dx, tip.dy)
    ..lineTo(tip.dx - 4, tip.dy + 8)
    ..lineTo(tip.dx + 4, tip.dy + 8)
    ..close();
  canvas.drawPath(head, Paint()..color = AppColors.ink);
  final tp = TextPainter(textDirection: TextDirection.ltr)
    ..text = TextSpan(text: '北', style: AppType.caption.copyWith(color: AppColors.ink, fontWeight: FontWeight.w600))
    ..layout();
  tp.paint(canvas, Offset(tip.dx + 6, tip.dy - 2));
}

void _drawParallelMarks(Canvas canvas, Offset mid, Offset unit, int count, Color color) {
  final normal = Offset(-unit.dy, unit.dx);
  final paint = Paint()
    ..color = color
    ..strokeWidth = 1.7
    ..style = PaintingStyle.stroke
    ..strokeCap = StrokeCap.round;
  for (var i = 0; i < count; i++) {
    final center = mid + unit * ((i - (count - 1) / 2) * 8);
    final tip = center + unit * 6;
    canvas.drawLine(tip, center + normal * 3.2, paint);
    canvas.drawLine(tip, center - normal * 3.2, paint);
  }
}

void _drawMarkedAngle(
  Canvas canvas,
  TextPainter tp,
  Offset vertex,
  Offset armFrom,
  Offset armTo, {
  required bool right,
  required String label,
}) {
  final ang1 = math.atan2(armFrom.dy - vertex.dy, armFrom.dx - vertex.dx);
  final ang2 = math.atan2(armTo.dy - vertex.dy, armTo.dx - vertex.dx);
  var sweep = ang2 - ang1;
  while (sweep <= -math.pi) {
    sweep += math.pi * 2;
  }
  while (sweep > math.pi) {
    sweep -= math.pi * 2;
  }
  final paint = Paint()
    ..color = AppColors.primary
    ..style = PaintingStyle.stroke
    ..strokeWidth = 1.6;
  if (right) {
    const side = 12.0;
    final u1 = Offset(math.cos(ang1), math.sin(ang1));
    final u2 = Offset(math.cos(ang2), math.sin(ang2));
    final path = Path()
      ..moveTo((vertex + u1 * side).dx, (vertex + u1 * side).dy)
      ..lineTo((vertex + u1 * side + u2 * side).dx, (vertex + u1 * side + u2 * side).dy)
      ..lineTo((vertex + u2 * side).dx, (vertex + u2 * side).dy);
    canvas.drawPath(path, paint);
  } else {
    canvas.drawArc(Rect.fromCircle(center: vertex, radius: 22), ang1, sweep, false, paint);
  }
  if (label.isEmpty) return;
  final mid = ang1 + sweep / 2;
  final at = vertex + Offset(math.cos(mid), math.sin(mid)) * (right ? 28 : 36);
  tp.text = TextSpan(
    text: label,
    style: AppType.caption.copyWith(color: AppColors.primary, fontWeight: FontWeight.w600),
  );
  tp.layout();
  tp.paint(canvas, at - Offset(tp.width / 2, tp.height / 2));
}

class StatsPainter extends CustomPainter {
  StatsPainter(this.figure);

  final Map<String, dynamic> figure;

  static const _fills = <Color>[
    AppColors.primary,
    AppColors.slate,
    AppColors.warning,
    AppColors.success,
    AppColors.charcoal,
    AppColors.hairlineStrong,
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final type = (figure['type'] ?? '').toString();
    final items = <Map>[];
    final raw = figure['items'];
    if (raw is List) {
      for (final item in raw) {
        if (item is Map) items.add(item);
      }
    }
    if (items.isEmpty) return;
    final title = (figure['title'] ?? '').toString();
    final top = title.isEmpty ? 8.0 : 28.0;
    if (title.isNotEmpty) {
      final tp = TextPainter(textDirection: TextDirection.ltr)
        ..text = TextSpan(text: title, style: AppType.caption.copyWith(color: AppColors.ink, fontWeight: FontWeight.w600))
        ..layout(maxWidth: size.width - 16);
      tp.paint(canvas, const Offset(8, 4));
    }
    if (type == 'pie_chart') {
      _pie(canvas, size, items, top);
    } else if (type == 'line_chart') {
      _line(canvas, size, items, top);
    } else {
      _bars(canvas, size, items, top, touching: type == 'histogram');
    }
  }

  void _bars(Canvas canvas, Size size, List<Map> items, double top, {required bool touching}) {
    var maxV = 1.0;
    for (final item in items) {
      final value = (item['value'] as num?)?.toDouble() ?? 0;
      if (value > maxV) maxV = value;
    }
    final bottom = size.height - 28;
    final usable = math.max(bottom - top, 20);
    final slot = (size.width - 24) / items.length;
    final gap = touching ? 0.0 : math.min(10.0, slot * 0.25);
    final tp = TextPainter(textDirection: TextDirection.ltr);
    for (var i = 0; i < items.length; i++) {
      final value = (items[i]['value'] as num?)?.toDouble() ?? 0;
      final barH = usable * (value / maxV);
      final left = 12 + slot * i + gap / 2;
      final rect = Rect.fromLTWH(left, bottom - barH, math.max(slot - gap, 4), barH);
      canvas.drawRect(rect, Paint()..color = _fills[i % _fills.length]);
      tp.text = TextSpan(
        text: (items[i]['label'] ?? '').toString(),
        style: AppType.caption.copyWith(color: AppColors.slate),
      );
      tp.layout(maxWidth: slot);
      tp.paint(canvas, Offset(left, bottom + 4));
    }
  }

  void _line(Canvas canvas, Size size, List<Map> items, double top) {
    var maxV = 1.0;
    for (final item in items) {
      final value = (item['value'] as num?)?.toDouble() ?? 0;
      if (value > maxV) maxV = value;
    }
    final bottom = size.height - 28;
    final usable = math.max(bottom - top, 20);
    final step = items.length == 1 ? 0.0 : (size.width - 36) / (items.length - 1);
    final points = <Offset>[];
    for (var i = 0; i < items.length; i++) {
      final value = (items[i]['value'] as num?)?.toDouble() ?? 0;
      points.add(Offset(18 + step * i, bottom - usable * (value / maxV)));
    }
    final paint = Paint()
      ..color = AppColors.primary
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    for (var i = 0; i < points.length - 1; i++) {
      canvas.drawLine(points[i], points[i + 1], paint);
    }
    final tp = TextPainter(textDirection: TextDirection.ltr);
    for (var i = 0; i < points.length; i++) {
      canvas.drawCircle(points[i], 4, Paint()..color = AppColors.primary);
      tp.text = TextSpan(
        text: (items[i]['label'] ?? '').toString(),
        style: AppType.caption.copyWith(color: AppColors.slate),
      );
      tp.layout();
      tp.paint(canvas, Offset(points[i].dx - tp.width / 2, bottom + 4));
    }
  }

  void _pie(Canvas canvas, Size size, List<Map> items, double top) {
    var total = 0.0;
    for (final item in items) {
      total += (item['value'] as num?)?.toDouble() ?? 0;
    }
    if (total <= 0) return;
    final radius = math.min(size.width * 0.28, (size.height - top) * 0.42);
    final center = Offset(size.width * 0.32, top + (size.height - top) / 2);
    var start = -math.pi / 2;
    final tp = TextPainter(textDirection: TextDirection.ltr);
    for (var i = 0; i < items.length; i++) {
      final value = (items[i]['value'] as num?)?.toDouble() ?? 0;
      final sweep = value / total * math.pi * 2;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        start,
        sweep,
        true,
        Paint()..color = _fills[i % _fills.length],
      );
      final legendY = top + i * 18;
      final color = _fills[i % _fills.length];
      canvas.drawRect(Rect.fromLTWH(size.width * 0.62, legendY, 12, 12), Paint()..color = color);
      tp.text = TextSpan(
        text: '${items[i]['label']}  ${value.toStringAsFixed(value == value.roundToDouble() ? 0 : 1)}',
        style: AppType.caption.copyWith(color: AppColors.ink),
      );
      tp.layout(maxWidth: size.width * 0.34);
      tp.paint(canvas, Offset(size.width * 0.62 + 16, legendY - 1));
      start += sweep;
    }
  }

  @override
  bool shouldRepaint(covariant StatsPainter oldDelegate) => oldDelegate.figure != figure;
}

class GridFigurePainter extends CustomPainter {
  GridFigurePainter(this.figure);

  final Map<String, dynamic> figure;

  @override
  void paint(Canvas canvas, Size size) {
    final type = (figure['type'] ?? '').toString();
    if (type == 'net') {
      _net(canvas, size);
    } else {
      _views(canvas, size);
    }
  }

  void _views(Canvas canvas, Size size) {
    final panels = <(String, List)>[
      ('从前面看', (figure['front'] as List?) ?? const []),
      ('从左面看', (figure['left'] as List?) ?? const []),
      ('从上面看', (figure['top'] as List?) ?? const []),
    ];
    final shown = panels.where((panel) => panel.$2.isNotEmpty).toList();
    if (shown.isEmpty) return;
    final slot = size.width / shown.length;
    var maxCols = 1;
    var maxRows = 1;
    for (final panel in shown) {
      maxCols = math.max(maxCols, _gridCols(panel.$2));
      maxRows = math.max(maxRows, _gridRows(panel.$2));
    }
    final cell = math.min((slot - 16) / maxCols, (size.height - 36) / maxRows);
    for (var i = 0; i < shown.length; i++) {
      _labeledGrid(
        canvas,
        shown[i].$1,
        shown[i].$2,
        Offset(slot * i, 0),
        Size(slot, size.height),
        cellSize: cell,
        alignBottom: true,
      );
    }
  }

  void _net(Canvas canvas, Size size) {
    _labeledGrid(canvas, '展开图', (figure['cells'] as List?) ?? const [], Offset.zero, size, labels: figure['labels']);
  }

  void _labeledGrid(
    Canvas canvas,
    String title,
    List grid,
    Offset origin,
    Size area, {
    Object? labels,
    double? cellSize,
    bool alignBottom = false,
  }) {
    final rows = <List>[];
    for (final row in grid) {
      if (row is List && row.isNotEmpty) rows.add(row);
    }
    if (rows.isEmpty) return;
    final cols = rows.map((row) => row.length).reduce(math.max);
    final tp = TextPainter(textDirection: TextDirection.ltr)
      ..text = TextSpan(text: title, style: AppType.caption.copyWith(color: AppColors.ink, fontWeight: FontWeight.w600))
      ..layout(maxWidth: area.width - 8);
    tp.paint(canvas, origin + const Offset(6, 2));
    final cell = cellSize ?? math.min((area.width - 16) / cols, (area.height - 28) / rows.length);
    final gridW = cell * cols;
    final gridH = cell * rows.length;
    final left = origin.dx + (area.width - gridW) / 2;
    final top = alignBottom ? origin.dy + area.height - 8 - gridH : origin.dy + 22;
    final border = Paint()
      ..color = AppColors.ink
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    final fill = Paint()..color = AppColors.lavender;
    for (var r = 0; r < rows.length; r++) {
      for (var c = 0; c < rows[r].length; c++) {
        final value = rows[r][c];
        final n = value is num ? value.toInt() : int.tryParse('$value') ?? 0;
        if (n == 0) continue;
        final rect = Rect.fromLTWH(left + c * cell, top + r * cell, cell, cell);
        canvas.drawRect(rect, fill);
        canvas.drawRect(rect, border);
        var text = n > 1 ? '$n' : '';
        if (labels is List && r < labels.length && labels[r] is List && c < (labels[r] as List).length) {
          final mark = '${(labels[r] as List)[c]}';
          if (mark.isNotEmpty && mark != 'null') text = mark;
        }
        if (text.isEmpty) continue;
        final label = TextPainter(textDirection: TextDirection.ltr)
          ..text = TextSpan(text: text, style: AppType.caption.copyWith(color: AppColors.ink, fontWeight: FontWeight.w600))
          ..layout();
        label.paint(canvas, rect.center - Offset(label.width / 2, label.height / 2));
      }
    }
  }

  @override
  bool shouldRepaint(covariant GridFigurePainter oldDelegate) => oldDelegate.figure != figure;
}

int _gridCols(List grid) {
  var cols = 0;
  for (final row in grid) {
    if (row is List && row.length > cols) cols = row.length;
  }
  return cols;
}

int _gridRows(List grid) {
  var rows = 0;
  for (final row in grid) {
    if (row is List && row.isNotEmpty) rows += 1;
  }
  return rows;
}
