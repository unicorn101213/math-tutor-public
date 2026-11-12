import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'theme.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key, required this.api, required this.onDone});

  final TutorApi api;
  final VoidCallback onDone;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _phone = TextEditingController();
  final _code = TextEditingController();
  var _busy = false;
  var _notice = '填手机号。验证码由给你安装包的人转告，第一次登录送 5 次讲解。';
  var _feedback = '';
  var _feedbackBad = false;

  @override
  void dispose() {
    _phone.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _askCode() async {
    setState(() => _busy = true);
    try {
      final res = await widget.api.requestCode(_phone.text);
      if (!mounted) return;
      setState(() {
        _feedbackBad = false;
        _feedback = (res['message'] as String?) ?? '请向给你安装包的人要验证码。';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _feedbackBad = true;
        _feedback = '现在连不上。过一会儿再要验证码。';
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _enter() async {
    if (_phone.text.trim().length != 11 || _code.text.trim().length != 6) {
      setState(() {
        _feedbackBad = true;
        _feedback = '请填 11 位手机号，再填 6 位验证码。';
      });
      return;
    }
    setState(() {
      _busy = true;
      _feedback = '正在登录…';
      _feedbackBad = false;
    });
    try {
      final res = await widget.api.verifyCode(_phone.text, _code.text);
      if (!mounted) return;
      if (res['ok'] == true) {
        widget.onDone();
        return;
      }
      setState(() {
        _feedbackBad = true;
        _feedback = (res['message'] as String?) ?? '验证码不对。';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _feedbackBad = true;
        _feedback = '现在连不上。过一会儿再登录。';
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 36, 20, 24),
          children: [
            const Text('用手机号登录', style: AppType.title),
            const SizedBox(height: 8),
            Text(_notice, style: AppType.small),
            const SizedBox(height: 24),
            TextField(
              controller: _phone,
              keyboardType: TextInputType.phone,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(11)],
              decoration: const InputDecoration(
                labelText: '手机号',
                filled: true,
                fillColor: AppColors.canvas,
                border: OutlineInputBorder(borderSide: BorderSide(color: AppColors.hairline)),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _code,
              keyboardType: TextInputType.number,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) {
                if (!_busy) _enter();
              },
              inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
              decoration: const InputDecoration(
                labelText: '验证码',
                filled: true,
                fillColor: AppColors.canvas,
                border: OutlineInputBorder(borderSide: BorderSide(color: AppColors.hairline)),
              ),
            ),
            const SizedBox(height: 16),
            if (_feedback.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  _feedback,
                  style: AppType.body.copyWith(color: _feedbackBad ? AppColors.error : AppColors.ink),
                ),
              ),
            FilledButton(
              onPressed: _busy ? null : _enter,
              style: FilledButton.styleFrom(backgroundColor: AppColors.primary, foregroundColor: AppColors.onPrimary),
              child: Text(_busy ? '正在登录…' : '登录'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: _busy ? null : _askCode,
              child: const Text('向安装包的人要验证码'),
            ),
          ],
        ),
      ),
    );
  }
}
