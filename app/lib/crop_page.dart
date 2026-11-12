import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;

import 'theme.dart';

/// 把归一化选区（相对整图 0~1）裁成 JPEG。选区贴边时仍按像素裁切。
Uint8List cropToJpeg(img.Image source, Rect norm, {int quality = 85}) {
  final width = source.width;
  final height = source.height;
  var x = (norm.left * width).floor();
  var y = (norm.top * height).floor();
  var w = (norm.width * width).round();
  var h = (norm.height * height).round();
  x = x.clamp(0, width - 1);
  y = y.clamp(0, height - 1);
  if (x + w > width) w = width - x;
  if (y + h > height) h = height - y;
  if (w < 1) w = 1;
  if (h < 1) h = 1;
  final cropped = img.copyCrop(source, x: x, y: y, width: w, height: h);
  return Uint8List.fromList(img.encodeJpg(cropped, quality: quality));
}

/// 沿笔迹把像素打成色块。块内取平均色，细线和下划线答案会看不清。
void paintMosaic(img.Image image, List<Offset> points, {required double radius, int? block}) {
  if (points.isEmpty || radius < 1 || image.width < 2 || image.height < 2) return;
  final cell = (block ?? math.max(6, math.min(28, (radius * 0.5).round()))).clamp(2, 64);
  var minX = image.width.toDouble();
  var minY = image.height.toDouble();
  var maxX = 0.0;
  var maxY = 0.0;
  for (final p in points) {
    minX = math.min(minX, p.dx - radius);
    minY = math.min(minY, p.dy - radius);
    maxX = math.max(maxX, p.dx + radius);
    maxY = math.max(maxY, p.dy + radius);
  }
  final x1 = math.min(image.width, maxX.ceil());
  final y1 = math.min(image.height, maxY.ceil());
  final startX = ((minX.floor() ~/ cell) * cell).clamp(0, image.width - 1);
  final startY = ((minY.floor() ~/ cell) * cell).clamp(0, image.height - 1);

  for (var by = startY; by < y1; by += cell) {
    for (var bx = startX; bx < x1; bx += cell) {
      if (_strokeDistance(bx + cell / 2, by + cell / 2, points) > radius) continue;
      var r = 0;
      var g = 0;
      var b = 0;
      var n = 0;
      final yEnd = math.min(by + cell, image.height);
      final xEnd = math.min(bx + cell, image.width);
      for (var y = by; y < yEnd; y++) {
        for (var x = bx; x < xEnd; x++) {
          final p = image.getPixel(x, y);
          r += p.r.toInt();
          g += p.g.toInt();
          b += p.b.toInt();
          n++;
        }
      }
      if (n == 0) continue;
      final cr = r ~/ n;
      final cg = g ~/ n;
      final cb = b ~/ n;
      for (var y = by; y < yEnd; y++) {
        for (var x = bx; x < xEnd; x++) {
          image.setPixelRgb(x, y, cr, cg, cb);
        }
      }
    }
  }
}

double _strokeDistance(double x, double y, List<Offset> points) {
  var best = double.infinity;
  for (final p in points) {
    final dx = x - p.dx;
    final dy = y - p.dy;
    final d = math.sqrt(dx * dx + dy * dy);
    if (d < best) best = d;
  }
  for (var i = 1; i < points.length; i++) {
    final d = _distToSegment(x, y, points[i - 1], points[i]);
    if (d < best) best = d;
  }
  return best;
}

double _distToSegment(double x, double y, Offset a, Offset b) {
  final abx = b.dx - a.dx;
  final aby = b.dy - a.dy;
  final len2 = abx * abx + aby * aby;
  if (len2 == 0) {
    final dx = x - a.dx;
    final dy = y - a.dy;
    return math.sqrt(dx * dx + dy * dy);
  }
  final t = (((x - a.dx) * abx + (y - a.dy) * aby) / len2).clamp(0.0, 1.0);
  final px = a.dx + abx * t;
  final py = a.dy + aby * t;
  final dx = x - px;
  final dy = y - py;
  return math.sqrt(dx * dx + dy * dy);
}

enum _DragMode { move, draw, left, right, top, bottom, topLeft, topRight, bottomLeft, bottomRight }

enum _Tool { crop, mosaic, pan }

class _MosaicStroke {
  _MosaicStroke(this.points, this.radius);

  final List<Offset> points;
  final double radius;
}

/// 拍照或选图之后：框选题目，并可放大后把答案涂成马赛克。取消返回 null。
class ImageCropPage extends StatefulWidget {
  const ImageCropPage({super.key, required this.bytes, this.stepLabel});

  final Uint8List bytes;
  final String? stepLabel;

  @override
  State<ImageCropPage> createState() => _ImageCropPageState();
}

class _ImageCropPageState extends State<ImageCropPage> {
  static const _initial = Rect.fromLTRB(0.12, 0.16, 0.88, 0.84);

  img.Image? _src;
  Uint8List? _preview;
  var _failed = false;
  var _working = false;
  Rect _norm = _initial;
  Rect? _before;
  _DragMode? _mode;
  Offset? _drawAnchor;
  Rect? _imageRect;
  Size? _viewportSize;

  _Tool _tool = _Tool.crop;
  double _viewScale = 1;
  Offset _viewOffset = Offset.zero;
  var _multi = false;
  double _scaleAtStart = 1;
  Offset? _contentFocal;
  double _brushScreen = 24;
  List<Offset>? _live;
  double _liveRadius = 24;
  final _strokes = <_MosaicStroke>[];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final decoded = img.decodeImage(widget.bytes);
    if (!mounted) return;
    if (decoded == null) {
      setState(() {
        _failed = true;
        _preview = widget.bytes;
      });
      return;
    }
    final oriented = img.bakeOrientation(decoded);
    final preview = Uint8List.fromList(img.encodeJpg(oriented, quality: 82));
    if (!mounted) return;
    setState(() {
      _src = oriented;
      _preview = preview;
    });
  }

  img.Image _editedImage() {
    final src = _src!;
    if (_strokes.isEmpty) return src;
    final copy = src.clone();
    for (final stroke in _strokes) {
      paintMosaic(copy, stroke.points, radius: stroke.radius);
    }
    return copy;
  }

  void _refreshPreview() {
    final edited = _editedImage();
    setState(() {
      _preview = Uint8List.fromList(img.encodeJpg(edited, quality: 80));
    });
  }

  void _useFullFrame() {
    if (_working) return;
    if (_strokes.isEmpty || _src == null) {
      Navigator.of(context).pop(widget.bytes);
      return;
    }
    _working = true;
    final bytes = Uint8List.fromList(img.encodeJpg(_editedImage(), quality: 85));
    if (!mounted) return;
    Navigator.of(context).pop(bytes);
  }

  Future<void> _confirm() async {
    final src = _src;
    if (src == null || _working) {
      Navigator.of(context).pop(widget.bytes);
      return;
    }
    final nearlyFull = _norm.left <= 0.01 &&
        _norm.top <= 0.01 &&
        _norm.right >= 0.99 &&
        _norm.bottom >= 0.99;
    if (nearlyFull && _strokes.isEmpty) {
      Navigator.of(context).pop(widget.bytes);
      return;
    }
    _working = true;
    final bytes = cropToJpeg(_editedImage(), _norm);
    if (!mounted) return;
    Navigator.of(context).pop(bytes);
  }

  void _undo() {
    if (_strokes.isEmpty || _working) return;
    _strokes.removeLast();
    _refreshPreview();
  }

  void _bumpZoom(double factor) {
    final size = _viewportSize;
    final next = (_viewScale * factor).clamp(1.0, 6.0);
    if (size == null) {
      setState(() => _viewScale = next);
      return;
    }
    final center = Offset(size.width / 2, size.height / 2);
    final content = (center - _viewOffset) / _viewScale;
    setState(() {
      _viewScale = next;
      _viewOffset = _clampOffset(center - content * next, next, size);
    });
  }

  void _resetZoom() {
    setState(() {
      _viewScale = 1;
      _viewOffset = Offset.zero;
    });
  }

  Offset _clampOffset(Offset offset, double scale, Size viewport) {
    if (viewport.width <= 0 || viewport.height <= 0 || scale <= 1) return Offset.zero;
    final minX = viewport.width * (1 - scale);
    final minY = viewport.height * (1 - scale);
    return Offset(offset.dx.clamp(minX, 0), offset.dy.clamp(minY, 0));
  }

  Offset _toContent(Offset viewportLocal) => (viewportLocal - _viewOffset) / _viewScale;

  Offset _normalize(Offset local, Rect imageRect) {
    final nx = ((local.dx - imageRect.left) / imageRect.width).clamp(0.0, 1.0);
    final ny = ((local.dy - imageRect.top) / imageRect.height).clamp(0.0, 1.0);
    return Offset(nx, ny);
  }

  Rect _selectionIn(Rect imageRect) {
    return Rect.fromLTRB(
      imageRect.left + _norm.left * imageRect.width,
      imageRect.top + _norm.top * imageRect.height,
      imageRect.left + _norm.right * imageRect.width,
      imageRect.top + _norm.bottom * imageRect.height,
    );
  }

  _DragMode? _hit(Offset p, Rect box) {
    const slop = 28.0;
    bool near(Offset a) => (p - a).distance <= slop;
    if (near(box.topLeft)) return _DragMode.topLeft;
    if (near(box.topRight)) return _DragMode.topRight;
    if (near(box.bottomLeft)) return _DragMode.bottomLeft;
    if (near(box.bottomRight)) return _DragMode.bottomRight;
    final onLeft = (p.dx - box.left).abs() <= slop && p.dy >= box.top && p.dy <= box.bottom;
    final onRight = (p.dx - box.right).abs() <= slop && p.dy >= box.top && p.dy <= box.bottom;
    final onTop = (p.dy - box.top).abs() <= slop && p.dx >= box.left && p.dx <= box.right;
    final onBottom = (p.dy - box.bottom).abs() <= slop && p.dx >= box.left && p.dx <= box.right;
    if (onLeft) return _DragMode.left;
    if (onRight) return _DragMode.right;
    if (onTop) return _DragMode.top;
    if (onBottom) return _DragMode.bottom;
    if (box.contains(p)) return _DragMode.move;
    return null;
  }

  void _onScaleStart(ScaleStartDetails details) {
    _multi = details.pointerCount >= 2;
    if (_multi) {
      _scaleAtStart = _viewScale;
      _contentFocal = _toContent(details.localFocalPoint);
      _mode = null;
      _live = null;
      return;
    }
    if (_working) return;
    final content = _toContent(details.localFocalPoint);
    if (_tool == _Tool.pan) return;
    if (_tool == _Tool.mosaic) {
      if (_src == null) return;
      _live = [content];
      _liveRadius = _brushScreen / _viewScale;
      setState(() {});
      return;
    }
    final imageRect = _imageRect;
    if (imageRect == null) return;
    final box = _selectionIn(imageRect);
    final mode = _hit(content, box);
    _before = _norm;
    if (mode != null) {
      _mode = mode;
      _drawAnchor = null;
      return;
    }
    if (!imageRect.contains(content)) {
      _mode = null;
      return;
    }
    _mode = _DragMode.draw;
    _drawAnchor = _normalize(content, imageRect);
    final p = _drawAnchor!;
    setState(() => _norm = Rect.fromLTRB(p.dx, p.dy, p.dx, p.dy));
  }

  void _onScaleUpdate(ScaleUpdateDetails details) {
    if (_multi || details.pointerCount >= 2) {
      final focalContent = _contentFocal;
      final size = _viewportSize;
      if (!_multi || focalContent == null || size == null) return;
      final next = (_scaleAtStart * details.scale).clamp(1.0, 6.0);
      final offset = details.localFocalPoint - focalContent * next;
      setState(() {
        _viewScale = next;
        _viewOffset = _clampOffset(offset, next, size);
      });
      return;
    }
    if (_tool == _Tool.pan) {
      final size = _viewportSize;
      if (size == null) return;
      setState(() {
        _viewOffset = _clampOffset(_viewOffset + details.focalPointDelta, _viewScale, size);
      });
      return;
    }
    if (_tool == _Tool.mosaic) {
      if (_live == null) return;
      setState(() => _live!.add(_toContent(details.localFocalPoint)));
      return;
    }
    final imageRect = _imageRect;
    final mode = _mode;
    if (imageRect == null || mode == null) return;
    final content = _toContent(details.localFocalPoint);
    final delta = details.focalPointDelta / _viewScale;
    final dx = delta.dx / imageRect.width;
    final dy = delta.dy / imageRect.height;
    final minW = (36 / imageRect.width).clamp(0.04, 0.5);
    final minH = (36 / imageRect.height).clamp(0.04, 0.5);
    setState(() {
      if (mode == _DragMode.draw && _drawAnchor != null) {
        _norm = _fromPoints(_drawAnchor!, _normalize(content, imageRect));
        return;
      }
      var n = _norm;
      switch (mode) {
        case _DragMode.move:
          final w = n.width;
          final h = n.height;
          n = Rect.fromLTWH((n.left + dx).clamp(0.0, 1.0 - w), (n.top + dy).clamp(0.0, 1.0 - h), w, h);
        case _DragMode.left:
          n = Rect.fromLTRB((n.left + dx).clamp(0.0, n.right - minW), n.top, n.right, n.bottom);
        case _DragMode.right:
          n = Rect.fromLTRB(n.left, n.top, (n.right + dx).clamp(n.left + minW, 1.0), n.bottom);
        case _DragMode.top:
          n = Rect.fromLTRB(n.left, (n.top + dy).clamp(0.0, n.bottom - minH), n.right, n.bottom);
        case _DragMode.bottom:
          n = Rect.fromLTRB(n.left, n.top, n.right, (n.bottom + dy).clamp(n.top + minH, 1.0));
        case _DragMode.topLeft:
          n = Rect.fromLTRB(
            (n.left + dx).clamp(0.0, n.right - minW),
            (n.top + dy).clamp(0.0, n.bottom - minH),
            n.right,
            n.bottom,
          );
        case _DragMode.topRight:
          n = Rect.fromLTRB(
            n.left,
            (n.top + dy).clamp(0.0, n.bottom - minH),
            (n.right + dx).clamp(n.left + minW, 1.0),
            n.bottom,
          );
        case _DragMode.bottomLeft:
          n = Rect.fromLTRB(
            (n.left + dx).clamp(0.0, n.right - minW),
            n.top,
            n.right,
            (n.bottom + dy).clamp(n.top + minH, 1.0),
          );
        case _DragMode.bottomRight:
          n = Rect.fromLTRB(
            n.left,
            n.top,
            (n.right + dx).clamp(n.left + minW, 1.0),
            (n.bottom + dy).clamp(n.top + minH, 1.0),
          );
        case _DragMode.draw:
          break;
      }
      _norm = n;
    });
  }

  void _onScaleEnd(ScaleEndDetails details) {
    if (!_multi && _tool == _Tool.mosaic) {
      _commitMosaic();
    }
    if (!_multi && _tool == _Tool.crop) {
      final imageRect = _imageRect;
      if (imageRect != null) {
        final minW = 36 / imageRect.width;
        final minH = 36 / imageRect.height;
        if (_norm.width < minW || _norm.height < minH) {
          _norm = _before ?? _initial;
        }
      }
    }
    _multi = false;
    _mode = null;
    _drawAnchor = null;
    _contentFocal = null;
    if (mounted) setState(() {});
  }

  void _commitMosaic() {
    final src = _src;
    final rect = _imageRect;
    final live = _live;
    _live = null;
    if (src == null || rect == null || live == null || rect.width <= 0) return;
    final points = <Offset>[];
    for (final p in live) {
      if (!rect.contains(p)) continue;
      final nx = (p.dx - rect.left) / rect.width;
      final ny = (p.dy - rect.top) / rect.height;
      points.add(Offset(nx * src.width, ny * src.height));
    }
    if (points.isEmpty) return;
    final radius = _liveRadius * (src.width / rect.width);
    _strokes.add(_MosaicStroke(points, radius));
    _refreshPreview();
  }

  Rect _fromPoints(Offset a, Offset b) {
    return Rect.fromLTRB(
      math.min(a.dx, b.dx),
      math.min(a.dy, b.dy),
      math.max(a.dx, b.dx),
      math.max(a.dy, b.dy),
    );
  }

  @override
  Widget build(BuildContext context) {
    final preview = _preview;
    final step = widget.stepLabel;
    final hint = _tool == _Tool.mosaic
        ? '放大后沿下划线涂掉答案'
        : _tool == _Tool.pan
            ? '拖动查看放大的画面'
            : '拖边角调整，或在暗处重新拉一个框';
    return Scaffold(
      backgroundColor: AppColors.ink,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 4, 4, 0),
              child: Row(
                children: [
                  TextButton(
                    onPressed: _working ? null : () => Navigator.of(context).pop(),
                    child: Text('取消', style: AppType.button.copyWith(color: AppColors.onPrimary)),
                  ),
                  Expanded(
                    child: Text(
                      step ?? '框选题目',
                      textAlign: TextAlign.center,
                      style: AppType.bodyMedium.copyWith(color: AppColors.onPrimary),
                    ),
                  ),
                  TextButton(
                    onPressed: _working ? null : _useFullFrame,
                    child: Text('用整张', style: AppType.button.copyWith(color: AppColors.onPrimary)),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 6),
              child: Text(hint, style: AppType.caption.copyWith(color: AppColors.onPrimary.withOpacity(0.78))),
            ),
            SizedBox(
              height: 36,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: [
                  _chip('框选', _tool == _Tool.crop, () => setState(() => _tool = _Tool.crop)),
                  _chip('涂抹', _tool == _Tool.mosaic, _src == null ? null : () => setState(() => _tool = _Tool.mosaic)),
                  _chip('移动', _tool == _Tool.pan, () => setState(() => _tool = _Tool.pan)),
                  _chip('放大', false, () => _bumpZoom(1.35)),
                  _chip('缩小', false, () => _bumpZoom(1 / 1.35)),
                  if (_viewScale > 1.05) _chip('还原', false, _resetZoom),
                  _chip('撤销', false, _strokes.isEmpty ? null : _undo),
                ],
              ),
            ),
            if (_tool == _Tool.mosaic)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    _chip('细', _brushScreen == 14, () => setState(() => _brushScreen = 14)),
                    _chip('中', _brushScreen == 24, () => setState(() => _brushScreen = 24)),
                    _chip('粗', _brushScreen == 40, () => setState(() => _brushScreen = 40)),
                  ],
                ),
              ),
            Expanded(
              child: preview == null
                  ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
                  : LayoutBuilder(
                      builder: (context, constraints) {
                        final viewport = Size(constraints.maxWidth, constraints.maxHeight);
                        _viewportSize = viewport;
                        final imageRect = _containRect(
                          viewport,
                          Size((_src?.width ?? 1).toDouble(), (_src?.height ?? 1).toDouble()),
                        );
                        _imageRect = imageRect;
                        final selection = _selectionIn(imageRect);
                        return ClipRect(
                          child: GestureDetector(
                            key: const Key('crop-surface'),
                            behavior: HitTestBehavior.opaque,
                            onScaleStart: _onScaleStart,
                            onScaleUpdate: _onScaleUpdate,
                            onScaleEnd: _onScaleEnd,
                            child: Transform(
                              transform: Matrix4.identity()
                                ..translate(_viewOffset.dx, _viewOffset.dy)
                                ..scale(_viewScale),
                              alignment: Alignment.topLeft,
                              child: Stack(
                                children: [
                                  Positioned.fromRect(
                                    rect: imageRect,
                                    child: Image.memory(preview, fit: BoxFit.fill, gaplessPlayback: true),
                                  ),
                                  Positioned.fill(
                                    child: CustomPaint(
                                      painter: _CropOverlayPainter(
                                        selection: selection,
                                        dim: _tool == _Tool.crop,
                                        handles: _tool == _Tool.crop,
                                        livePoints: _live ?? const [],
                                        liveRadius: _liveRadius,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        );
                      },
                    ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: Column(
                children: [
                  Text(
                    _failed
                        ? '这张图没法裁切，可以改用整张。'
                        : '框外不会发送。涂掉的答案会留在图里，模型看不到。',
                    textAlign: TextAlign.center,
                    style: AppType.caption.copyWith(color: AppColors.onPrimary.withOpacity(0.78)),
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      style: FilledButton.styleFrom(
                        backgroundColor: AppColors.primary,
                        foregroundColor: AppColors.onPrimary,
                        disabledBackgroundColor: AppColors.hairline,
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                      onPressed: preview == null || _working ? null : _confirm,
                      child: Text(
                        _working ? '正在处理…' : '用这块',
                        style: AppType.button.copyWith(color: AppColors.onPrimary),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _chip(String label, bool selected, VoidCallback? onTap) {
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: TextButton(
        style: TextButton.styleFrom(
          backgroundColor: selected ? AppColors.primary : Colors.transparent,
          foregroundColor: AppColors.onPrimary,
          disabledForegroundColor: AppColors.stone,
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          minimumSize: const Size(0, 32),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: BorderSide(color: selected ? AppColors.primary : AppColors.onPrimary.withOpacity(0.4)),
          ),
        ),
        onPressed: _working ? null : onTap,
        child: Text(label, style: AppType.caption.copyWith(color: onTap == null ? AppColors.stone : AppColors.onPrimary, fontWeight: FontWeight.w600)),
      ),
    );
  }
}

Rect _containRect(Size viewport, Size image) {
  if (viewport.width <= 0 || viewport.height <= 0 || image.width <= 0 || image.height <= 0) {
    return Rect.zero;
  }
  final scale = math.min(viewport.width / image.width, viewport.height / image.height);
  final w = image.width * scale;
  final h = image.height * scale;
  return Rect.fromLTWH((viewport.width - w) / 2, (viewport.height - h) / 2, w, h);
}

class _CropOverlayPainter extends CustomPainter {
  _CropOverlayPainter({
    required this.selection,
    required this.dim,
    required this.handles,
    required this.livePoints,
    required this.liveRadius,
  });

  final Rect selection;
  final bool dim;
  final bool handles;
  final List<Offset> livePoints;
  final double liveRadius;

  @override
  void paint(Canvas canvas, Size size) {
    if (dim) {
      final shade = Path()
        ..addRect(Offset.zero & size)
        ..addRect(selection)
        ..fillType = PathFillType.evenOdd;
      canvas.drawPath(shade, Paint()..color = AppColors.ink.withOpacity(0.55));
      final grid = Paint()
        ..color = AppColors.onPrimary.withOpacity(0.35)
        ..strokeWidth = 1;
      for (var i = 1; i <= 2; i++) {
        final dx = selection.left + selection.width * i / 3;
        final dy = selection.top + selection.height * i / 3;
        canvas.drawLine(Offset(dx, selection.top), Offset(dx, selection.bottom), grid);
        canvas.drawLine(Offset(selection.left, dy), Offset(selection.right, dy), grid);
      }
    }

    canvas.drawRect(
      selection,
      Paint()
        ..color = AppColors.onPrimary
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );

    if (handles) {
      _bracket(canvas, selection.topLeft, const Offset(22, 0), const Offset(0, 22));
      _bracket(canvas, selection.topRight, const Offset(-22, 0), const Offset(0, 22));
      _bracket(canvas, selection.bottomLeft, const Offset(22, 0), const Offset(0, -22));
      _bracket(canvas, selection.bottomRight, const Offset(-22, 0), const Offset(0, -22));
    }

    if (livePoints.isNotEmpty && liveRadius > 0) {
      final cover = Paint()
        ..color = AppColors.ink.withOpacity(0.45)
        ..style = PaintingStyle.stroke
        ..strokeWidth = liveRadius * 2
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round;
      final path = Path()..moveTo(livePoints.first.dx, livePoints.first.dy);
      for (final p in livePoints.skip(1)) {
        path.lineTo(p.dx, p.dy);
      }
      canvas.drawPath(path, cover);
      canvas.drawCircle(livePoints.last, liveRadius, Paint()..color = AppColors.ink.withOpacity(0.45));
    }
  }

  void _bracket(Canvas canvas, Offset corner, Offset alongX, Offset alongY) {
    final paint = Paint()
      ..color = AppColors.primary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.square;
    final path = Path()
      ..moveTo(corner.dx + alongX.dx, corner.dy + alongX.dy)
      ..lineTo(corner.dx, corner.dy)
      ..lineTo(corner.dx + alongY.dx, corner.dy + alongY.dy);
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _CropOverlayPainter oldDelegate) {
    return oldDelegate.selection != selection ||
        oldDelegate.dim != dim ||
        oldDelegate.handles != handles ||
        oldDelegate.liveRadius != liveRadius ||
        oldDelegate.livePoints.length != livePoints.length;
  }
}
