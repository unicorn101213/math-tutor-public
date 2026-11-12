import 'dart:typed_data';

typedef ImagePasteCallback = void Function(Uint8List bytes);

class ClipboardPasteListener {
  ClipboardPasteListener(this.onImagePasted);
  final ImagePasteCallback onImagePasted;
  void dispose() {}
}

Future<Uint8List?> readClipboardImageBytes() async => null;
