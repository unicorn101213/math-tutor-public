import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:math_tutor/crop_page.dart';
import 'package:math_tutor/theme.dart';

Uint8List _twoToneJpeg() {
  final im = img.Image(width: 120, height: 80, numChannels: 3);
  img.fill(im, color: img.ColorRgb8(0, 0, 220));
  img.fillRect(im, x1: 0, y1: 0, x2: 59, y2: 79, color: img.ColorRgb8(220, 0, 0));
  return Uint8List.fromList(img.encodeJpg(im, quality: 95));
}

void main() {
  test('马赛克会把细黑线涂成浅色块', () {
    final source = img.Image(width: 80, height: 40, numChannels: 3);
    img.fill(source, color: img.ColorRgb8(255, 255, 255));
    for (var x = 8; x < 72; x++) {
      source.setPixelRgb(x, 20, 0, 0, 0);
    }
    paintMosaic(source, [const Offset(40, 20)], radius: 14, block: 8);
    final pixel = source.getPixel(40, 20);
    expect(pixel.r, greaterThan(80));
    expect(pixel.g, greaterThan(80));
    expect(pixel.b, greaterThan(80));
  });

  test('框选左半边后，裁出来的图更窄，而且是红的', () {
    final source = img.decodeImage(_twoToneJpeg())!;
    final croppedBytes = cropToJpeg(source, const Rect.fromLTRB(0, 0, 0.5, 1));
    final cropped = img.decodeImage(croppedBytes)!;
    expect(cropped.width, lessThan(source.width));
    expect(cropped.width, inInclusiveRange(55, 65));
    expect(cropped.height, inInclusiveRange(75, 80));
    final pixel = cropped.getPixel(cropped.width ~/ 2, cropped.height ~/ 2);
    expect(pixel.r, greaterThan(pixel.b));
  });

  testWidgets('取消不返回图片，用整张返回原图', (tester) async {
    final bytes = _twoToneJpeg();
    Uint8List? result = Uint8List(1);
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                result = await Navigator.of(context).push<Uint8List>(
                  MaterialPageRoute(builder: (_) => ImageCropPage(bytes: bytes)),
                );
              },
              child: const Text('打开'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('打开'));
    await tester.pumpAndSettle();
    expect(find.text('框选题目'), findsOneWidget);
    expect(find.text('涂抹'), findsOneWidget);
    expect(find.text('用这块'), findsOneWidget);

    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();
    expect(result, isNull);

    await tester.tap(find.text('打开'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('用整张'));
    await tester.pumpAndSettle();
    expect(result, bytes);
  });

  testWidgets('把右边框往里拖之后，裁出来的图更窄', (tester) async {
    final bytes = _twoToneJpeg();
    Uint8List? result;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                result = await Navigator.of(context).push<Uint8List>(
                  MaterialPageRoute(builder: (_) => ImageCropPage(bytes: bytes)),
                );
              },
              child: const Text('打开'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('打开'));
    await tester.pumpAndSettle();

    final surface = tester.getRect(find.byKey(const Key('crop-surface')));
    const image = Size(120, 80);
    final scale = math.min(surface.width / image.width, surface.height / image.height);
    final fitted = Size(image.width * scale, image.height * scale);
    final imageRect = Rect.fromLTWH(
      surface.left + (surface.width - fitted.width) / 2,
      surface.top + (surface.height - fitted.height) / 2,
      fitted.width,
      fitted.height,
    );
    final handle = Offset(
      imageRect.left + 0.88 * imageRect.width,
      imageRect.top + 0.5 * imageRect.height,
    );
    await tester.dragFrom(handle, Offset(-imageRect.width * 0.35, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('用这块'));
    await tester.pumpAndSettle();

    final cropped = img.decodeImage(result!)!;
    expect(cropped.width, lessThan(70));
  });
}
