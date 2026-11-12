import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'android_picker.dart';
import 'api.dart';
import 'chat_page.dart';
import 'grade_page.dart';
import 'grades.dart';
import 'login_page.dart';
import 'theme.dart';

const gradePrefKey = 'grade_id';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  enableAndroidPhotoPicker();
  runApp(const TutorApp());
}

class TutorApp extends StatelessWidget {
  const TutorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '数学家教',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: const StartPage(),
    );
  }
}

class StartPage extends StatefulWidget {
  const StartPage({super.key});

  @override
  State<StartPage> createState() => _StartPageState();
}

class _StartPageState extends State<StartPage> {
  String? _gradeId;
  var _loaded = false;
  var _needLogin = false;
  final _api = TutorApi();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString(gradePrefKey);
      var needLogin = false;
      try {
        final status = await _api.authStatus();
        needLogin = status['login_required'] == true;
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _gradeId = saved != null && gradeById(saved).id == saved ? saved : null;
        _needLogin = needLogin;
        _loaded = true;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _gradeId = null;
        _loaded = true;
      });
    }
  }

  Future<void> _save(String id) async {
    final grade = gradeById(id);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(gradePrefKey, grade.id);
    } catch (_) {}
    if (!mounted) return;
    setState(() => _gradeId = grade.id);
  }

  Future<void> _changeGrade() async {
    final picked = await Navigator.of(context).push<String>(
      MaterialPageRoute(
        builder: (context) => GradePage(
          selectedId: _gradeId,
          onPicked: (id) => Navigator.of(context).pop(id),
        ),
      ),
    );
    if (picked == null) return;
    await _save(picked);
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded) {
      return const Scaffold(
        backgroundColor: AppColors.surface,
        body: Center(child: CircularProgressIndicator(color: AppColors.primary)),
      );
    }
    if (_needLogin) {
      return LoginPage(
        api: _api,
        onDone: () => setState(() => _needLogin = false),
      );
    }
    final gradeId = _gradeId;
    if (gradeId == null) {
      return GradePage(onPicked: _save);
    }
    return ChatPage(
      api: _api,
      gradeId: gradeId,
      gradeLabel: gradeById(gradeId).label,
      onChangeGrade: _changeGrade,
    );
  }
}
