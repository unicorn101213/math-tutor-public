// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use
import 'dart:html' as html;
import 'dart:typed_data';

typedef ImagePasteCallback = void Function(Uint8List bytes);

class ClipboardPasteListener {
  ClipboardPasteListener(this.onImagePasted) {
    _pasteListener = (html.Event event) {
      if (event is html.ClipboardEvent) {
        _handlePaste(event);
      }
    };
    html.document.addEventListener('paste', _pasteListener, true);
  }

  final ImagePasteCallback onImagePasted;
  html.EventListener? _pasteListener;

  void _handlePaste(html.ClipboardEvent event) {
    final items = event.clipboardData?.items;
    if (items == null) return;
    final len = items.length ?? 0;
    var foundImage = false;
    for (var i = 0; i < len; i++) {
      final item = items[i];
      final type = item.type ?? '';
      if (type.startsWith('image/')) {
        final blob = item.getAsFile();
        if (blob != null) {
          foundImage = true;
          _readBlob(blob);
        }
      }
    }
    if (foundImage) {
      event.preventDefault();
    }
  }

  void _readBlob(html.Blob blob) {
    final reader = html.FileReader();
    reader.onLoadEnd.listen((_) {
      final res = reader.result;
      if (res is ByteBuffer) {
        onImagePasted(res.asUint8List());
      } else if (res is Uint8List) {
        onImagePasted(res);
      }
    });
    reader.readAsArrayBuffer(blob);
  }

  void dispose() {
    final listener = _pasteListener;
    if (listener != null) {
      html.document.removeEventListener('paste', listener, true);
    }
  }
}

Future<Uint8List?> readClipboardImageBytes() async {
  return null;
}
