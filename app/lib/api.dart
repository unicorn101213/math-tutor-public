import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

String apiBase() {
  const fromEnv = String.fromEnvironment('API_BASE');
  if (fromEnv.isNotEmpty) return fromEnv;
  return 'http://127.0.0.1:8300';
}

class RequestCancelledException implements Exception {
  const RequestCancelledException();
}

/// 连接被掐断、响应没读完、网关超时时值得再试一次。用户主动停止不算。
bool isTransientChatError(Object error) {
  if (error is RequestCancelledException) return false;
  if (error is TimeoutException || error is http.ClientException || error is FormatException) {
    return true;
  }
  final text = error.toString();
  return text.contains('服务暂时没接上（502') ||
      text.contains('服务暂时没接上（503') ||
      text.contains('服务暂时没接上（504');
}

class TutorApi {
  TutorApi({String? base, this.gradeId = 'j1'}) : base = base ?? apiBase();

  final String base;
  String gradeId;
  String? _deviceId;
  String? token;
  http.Client? _activeClient;
  int _activeSeq = 0;

  Future<String> deviceId() async {
    if (_deviceId != null) return _deviceId!;
    final prefs = await SharedPreferences.getInstance();
    _deviceId = prefs.getString('device_id_v2');
    if (_deviceId == null || _deviceId!.isEmpty) {
      final random = Random.secure();
      final bytes = List<int>.generate(16, (_) => random.nextInt(256));
      _deviceId = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
      await prefs.setString('device_id_v2', _deviceId!);
    }
    return _deviceId!;
  }

  Future<void> loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    token = prefs.getString('auth_token_v1');
  }

  Future<void> saveToken(String value) async {
    token = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('auth_token_v1', value);
  }

  Map<String, String> _headers({bool json = true}) {
    final headers = <String, String>{};
    if (json) headers['Content-Type'] = 'application/json';
    if (token != null && token!.isNotEmpty) headers['Authorization'] = 'Bearer $token';
    return headers;
  }

  void cancelCurrent() {
    _activeSeq++;
    _activeClient?.close();
    _activeClient = null;
  }

  Future<Map<String, dynamic>> chat({
    String? sessionId,
    String text = '',
    String? imageBase64,
    List<String>? imagesBase64,
    void Function()? onRetry,
  }) async {
    final id = await deviceId();
    final started = DateTime.now();
    for (var attempt = 0; attempt < 2; attempt++) {
      if (attempt == 1) {
        final seen = _activeSeq;
        onRetry?.call();
        await Future<void>.delayed(const Duration(milliseconds: 500));
        if (seen != _activeSeq) {
          throw const RequestCancelledException();
        }
      }
      try {
        return await _postChat(
          deviceIdValue: id,
          sessionId: sessionId,
          text: text,
          imageBase64: imageBase64,
          imagesBase64: imagesBase64,
        );
      } on RequestCancelledException {
        rethrow;
      } catch (e) {
        final fast = DateTime.now().difference(started) < const Duration(seconds: 8);
        if (attempt == 1 || !fast || !isTransientChatError(e)) rethrow;
      }
    }
    throw StateError('chat retry fell through');
  }

  Future<Map<String, dynamic>> _postChat({
    required String deviceIdValue,
    String? sessionId,
    String text = '',
    String? imageBase64,
    List<String>? imagesBase64,
  }) async {
    cancelCurrent();
    final mySeq = ++_activeSeq;
    final client = http.Client();
    _activeClient = client;

    try {
      final response = await client
          .post(
            Uri.parse('$base/chat'),
            headers: _headers(),
            body: jsonEncode({
              'device_id': deviceIdValue,
              'session_id': sessionId,
              'text': text,
              'image_base64': imageBase64,
              'images_base64': imagesBase64,
              'grade_id': gradeId,
            }),
          )
          .timeout(const Duration(seconds: 150));
      if (mySeq != _activeSeq) {
        throw const RequestCancelledException();
      }
      if (response.statusCode != 200) {
        throw Exception('服务暂时没接上（${response.statusCode}）');
      }
      return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    } catch (e) {
      if (mySeq != _activeSeq) {
        throw const RequestCancelledException();
      }
      rethrow;
    } finally {
      if (_activeClient == client) {
        _activeClient = null;
      }
      client.close();
    }
  }

  Future<Map<String, dynamic>> fetchKnowledge({String query = ''}) async {
    final id = await deviceId();
    final uri = Uri.parse('$base/knowledge').replace(queryParameters: {
      'device_id': id,
      'grade_id': gradeId,
      if (query.trim().isNotEmpty) 'q': query.trim(),
    });
    final response = await http.get(uri).timeout(const Duration(seconds: 25));
    if (response.statusCode != 200) {
      throw Exception('加载知识点库失败');
    }
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> fetchErrors({String chapterId = ''}) async {
    final id = await deviceId();
    final uri = Uri.parse('$base/errors').replace(queryParameters: {
      'device_id': id,
      'grade_id': gradeId,
      if (chapterId.trim().isNotEmpty) 'chapter_id': chapterId.trim(),
    });
    final response = await http.get(uri).timeout(const Duration(seconds: 25));
    if (response.statusCode != 200) {
      throw Exception('加载错题库失败');
    }
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Future<bool> deleteError(int errorId) async {
    final id = await deviceId();
    final response = await http
        .post(
          Uri.parse('$base/errors/delete'),
          headers: _headers(),
          body: jsonEncode({'device_id': id, 'error_id': errorId}),
        )
        .timeout(const Duration(seconds: 25));
    if (response.statusCode != 200) return false;
    final data = jsonDecode(utf8.decode(response.bodyBytes));
    return data is Map && data['ok'] == true;
  }

  Future<Map<String, dynamic>> pullTasks({String? sessionId}) async {
    final id = await deviceId();
    final response = await http
        .post(
          Uri.parse('$base/tasks/pull'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'device_id': id, 'session_id': sessionId}),
        )
        .timeout(const Duration(seconds: 25));
    if (response.statusCode != 200) {
      throw Exception('读取定时任务失败');
    }
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> fetchHistory({int afterId = 0, bool lite = false}) async {
    final id = await deviceId();
    final uri = Uri.parse('$base/history').replace(queryParameters: {
      'device_id': id,
      if (afterId > 0) 'after_id': '$afterId',
      if (lite) 'lite': '1',
    });
    final response = await http.get(uri).timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw Exception('加载历史记录失败');
    }
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Future<int> latestMessageId() async {
    final res = await fetchHistory(lite: true);
    final messages = (res['messages'] as List?) ?? const [];
    var maxId = 0;
    for (final item in messages) {
      if (item is! Map) continue;
      final id = int.tryParse('${item['id']}') ?? 0;
      if (id > maxId) maxId = id;
    }
    return maxId;
  }

  Future<Map<String, dynamic>?> replyAfter(int afterId) async {
    try {
      final res = await fetchHistory(afterId: afterId, lite: true);
      final messages = (res['messages'] as List?) ?? const [];
      Map? assistant;
      for (final item in messages) {
        if (item is Map && item['role'] == 'assistant') assistant = item;
      }
      if (assistant == null) return null;
      final blocks = assistant['blocks'];
      if (blocks is! List || blocks.isEmpty) return null;
      return {
        'session_id': assistant['session_id'] ?? res['session_id'],
        'blocks': blocks,
      };
    } catch (_) {
      return null;
    }
  }

  Future<void> clearHistory() async {
    final id = await deviceId();
    final response = await http
        .post(
          Uri.parse('$base/history/clear'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'device_id': id}),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw Exception('清除历史记录失败');
    }
  }

  Future<Map<String, dynamic>> authStatus() async {
    final id = await deviceId();
    await loadToken();
    final uri = Uri.parse('$base/auth/status').replace(queryParameters: {'device_id': id});
    final response = await http.get(uri, headers: _headers(json: false)).timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) throw Exception('登录状态没读到');
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> requestCode(String phone) async {
    final id = await deviceId();
    final response = await http
        .post(
          Uri.parse('$base/auth/sms'),
          headers: _headers(),
          body: jsonEncode({'phone': phone, 'device_id': id}),
        )
        .timeout(const Duration(seconds: 20));
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> verifyCode(String phone, String code) async {
    final id = await deviceId();
    final response = await http
        .post(
          Uri.parse('$base/auth/verify'),
          headers: _headers(),
          body: jsonEncode({'phone': phone, 'code': code, 'device_id': id}),
        )
        .timeout(const Duration(seconds: 20));
    final data = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    final tokenValue = data['token'] as String?;
    if (tokenValue != null && tokenValue.isNotEmpty) await saveToken(tokenValue);
    return data;
  }

  Future<Map<String, dynamic>> redeem(String code) async {
    final id = await deviceId();
    final response = await http
        .post(
          Uri.parse('$base/auth/redeem'),
          headers: _headers(),
          body: jsonEncode({'code': code, 'device_id': id}),
        )
        .timeout(const Duration(seconds: 20));
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }
}
