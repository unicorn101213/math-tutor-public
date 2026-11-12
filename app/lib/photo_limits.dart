import 'dart:typed_data';

import 'package:image/image.dart' as img;

const maxQuestionChars = 800;
const maxPhotosPerSend = 3;
const maxPhotoBytes = 1500 * 1024;
const maxPhotoTotalBytes = 4 * 1024 * 1024;
const maxPhotoEdge = 1600;

/// 发出去之前把长边压到 1600，并尽量把单张压到 1.5MB 以内。
Uint8List fitPhotoForSend(Uint8List bytes) {
  final decoded = img.decodeImage(bytes);
  if (decoded == null) return bytes;
  var image = decoded;
  final edge = image.width > image.height ? image.width : image.height;
  if (edge > maxPhotoEdge) {
    image = image.width >= image.height
        ? img.copyResize(image, width: maxPhotoEdge)
        : img.copyResize(image, height: maxPhotoEdge);
  }
  var quality = 82;
  var out = Uint8List.fromList(img.encodeJpg(image, quality: quality));
  while (out.length > maxPhotoBytes && quality > 45) {
    quality -= 8;
    out = Uint8List.fromList(img.encodeJpg(image, quality: quality));
  }
  return out;
}
