import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:math_tutor/api.dart';

void main() {
  test('连接中断、读断和网关超时可以再试一次', () {
    expect(isTransientChatError(TimeoutException('slow')), isTrue);
    expect(isTransientChatError(http.ClientException('Connection closed before full header was received')), isTrue);
    expect(isTransientChatError(const FormatException('truncated')), isTrue);
    expect(isTransientChatError(Exception('服务暂时没接上（504）')), isTrue);
    expect(isTransientChatError(Exception('服务暂时没接上（500）')), isFalse);
    expect(isTransientChatError(const RequestCancelledException()), isFalse);
  });
}
