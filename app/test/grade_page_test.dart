import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:math_tutor/grade_page.dart';
import 'package:math_tutor/theme.dart';

void main() {
  testWidgets('小学到初三都可以进入', (tester) async {
    String? picked;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: GradePage(onPicked: (id) => picked = id),
      ),
    );
    expect(find.text('一年级'), findsOneWidget);
    expect(find.text('初三'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const ValueKey('p1')));
    await tester.tap(find.byKey(const ValueKey('p1')));
    await tester.pump();
    expect(find.text('进入一年级'), findsOneWidget);
    await tester.tap(find.text('进入一年级'));
    expect(picked, 'p1');
  });
}
