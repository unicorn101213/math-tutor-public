import 'dart:io';
import 'dart:typed_data';

typedef ImagePasteCallback = void Function(Uint8List bytes);

class ClipboardPasteListener {
  ClipboardPasteListener(this.onImagePasted);
  final ImagePasteCallback onImagePasted;
  void dispose() {}
}

Future<Uint8List?> readClipboardImageBytes() async {
  if (!Platform.isWindows) return null;
  final tmpPath =
      '${Directory.systemTemp.path}${Platform.pathSeparator}tutor_clip_${DateTime.now().millisecondsSinceEpoch}.png';
  try {
    final script =
        "Add-Type -AssemblyName System.Windows.Forms; "
        "if ([System.Windows.Forms.Clipboard]::ContainsImage()) { "
        "\$img = [System.Windows.Forms.Clipboard]::GetImage(); "
        "\$img.Save('$tmpPath', [System.Drawing.Imaging.ImageFormat]::Png); "
        "Write-Output 'OK' }";
    final res = await Process.run('powershell', ['-NoProfile', '-Command', script]);
    if (res.exitCode == 0 && res.stdout.toString().contains('OK')) {
      final f = File(tmpPath);
      if (await f.exists()) {
        final bytes = await f.readAsBytes();
        await f.delete().catchError((_) => f);
        return bytes;
      }
    }
  } catch (_) {}
  return null;
}
