import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:math_tutor/api.dart';
import 'package:math_tutor/chat_page.dart';
import 'package:math_tutor/theme.dart';

class _HistoryApi extends TutorApi {
  _HistoryApi() : super(base: 'http://127.0.0.1:9');

  static final png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  );

  @override
  Future<Map<String, dynamic>> fetchHistory() async {
    return {
      'session_id': 's1',
      'messages': [
        {
          'role': 'user',
          'text': '[照片]第16题',
          'images': [base64Encode(png)],
          'blocks': <Map<String, dynamic>>[],
        },
      ],
    };
  }

  @override
  Future<Map<String, dynamic>> pullTasks({String? sessionId}) async {
    return {'session_id': sessionId, 'blocks': <Map<String, dynamic>>[]};
  }
}

class _KnowledgeApi extends _HistoryApi {
  @override
  Future<Map<String, dynamic>> fetchHistory() async => {
        'session_id': 's1',
        'messages': <Map<String, dynamic>>[],
      };

  @override
  Future<Map<String, dynamic>> fetchKnowledge({String query = ''}) async {
    return {
      'chapters': [
        {
          'id': 'ch1',
          'volume': '七年级上册',
          'title': '第一章 有理数',
          'intro': '正数和负数',
          'mindmap': <String>[],
          'nodes': [
            {'title': '正数和负数', 'volume': '七年级上册', 'summary': '七年级内容', 'mindmap': <String>[]},
          ],
        },
        {
          'id': 'ch19',
          'volume': '八年级下册',
          'title': '第十九章 二次根式',
          'intro': '二次根式',
          'mindmap': <String>[],
          'nodes': [
            {'title': '二次根式', 'volume': '八年级下册', 'summary': '八年级内容', 'mindmap': <String>[]},
          ],
        },
      ],
      'matched_nodes': <Map<String, dynamic>>[],
      'dynamic_cards': [
        {'title': '正数和负数', 'volume': '七年级上册', 'summary': '以前沉淀的七年级卡片', 'tags': '高频提问专题', 'mindmap': <String>[]},
      ],
    };
  }
}

void main() {
  testWidgets('打开就是对话，且包含拍照解题、错题库、知识点库三大入口', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: const ChatPage(),
      ),
    );
    expect(find.text('数学家教'), findsOneWidget);
    expect(find.text('拍照解题'), findsOneWidget);
    expect(find.text('错题库'), findsOneWidget);
    expect(find.text('知识点库'), findsOneWidget);
    expect(find.textContaining('拍给我'), findsOneWidget);
  });

  testWidgets('历史图片可以再放回待发送', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: ChatPage(api: _HistoryApi()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('再发一次'), findsOneWidget);
    await tester.tap(find.text('再发一次'));
    await tester.pump();
    expect(find.textContaining('待发送图片'), findsOneWidget);
    expect(_HistoryApi.png, isA<Uint8List>());
  });

  testWidgets('知识库按册次过滤，不把七年级卡片留在八年级里', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: ChatPage(api: _KnowledgeApi(), gradeId: 'j3', gradeLabel: '初三'),
      ),
    );
    await tester.pump();
    await tester.tap(find.text('知识点库'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('八年级下册'), findsOneWidget);
    await tester.tap(find.text('八年级下册'));
    await tester.pump();

    expect(find.text('第十九章 二次根式'), findsOneWidget);
    expect(find.text('二次根式'), findsOneWidget);
    expect(find.text('正数和负数'), findsNothing);
    expect(find.textContaining('对话动态沉淀专题'), findsNothing);
  });
}
