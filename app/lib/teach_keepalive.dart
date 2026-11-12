import 'package:flutter/services.dart';

const _channel = MethodChannel('com.family.math_tutor/teach');

Future<void> startTeachKeepAlive() async {
  try {
    await _channel.invokeMethod<void>('start');
  } catch (_) {}
}

Future<void> stopTeachKeepAlive() async {
  try {
    await _channel.invokeMethod<void>('stop');
  } catch (_) {}
}
