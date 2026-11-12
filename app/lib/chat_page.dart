import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import 'api.dart';
import 'clipboard_image.dart';
import 'crop_page.dart';
import 'figure_view.dart';
import 'photo_limits.dart';
import 'teach_keepalive.dart';
import 'theme.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key, this.api, this.gradeId = 'j1', this.gradeLabel = '初一', this.onChangeGrade});

  final TutorApi? api;
  final String gradeId;
  final String gradeLabel;
  final Future<void> Function()? onChangeGrade;

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> with WidgetsBindingObserver {
  late final TutorApi _api = widget.api ?? TutorApi();
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _picker = ImagePicker();
  final _pendingImages = <Uint8List>[];
  late final ClipboardPasteListener _pasteListener;

  final _messages = <_Message>[
    _Message.assistant(const [
      {
        'type': 'text',
        'text':
            '把不会的题拍给我（电脑端可直接 Ctrl+V 粘贴截图，支持多张图配文字一起发），或直接打字提问。下方可随时打开「错题库」和「知识点库」。',
      },
    ]),
  ];

  String? _sessionId;
  var _retrying = false;
  bool _sending = false;
  String _creditLabel = '';
  Timer? _taskTimer;
  Completer<void>? _wake;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _api.gradeId = widget.gradeId;
    _pasteListener = ClipboardPasteListener(_stagePastedImage);
    _boot();
    _loadCredits();
    _taskTimer = Timer.periodic(const Duration(seconds: 45), (_) => _pullTasks());
  }

  Future<void> _boot() async {
    await _loadHistory();
    await _catchUnfinished();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      final wake = _wake;
      if (wake != null && !wake.isCompleted) wake.complete();
    }
  }

  @override
  void didUpdateWidget(covariant ChatPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.gradeId != widget.gradeId) {
      _api.gradeId = widget.gradeId;
    }
  }

  Future<void> _loadCredits() async {
    try {
      final status = await _api.authStatus();
      if (!mounted) return;
      final unlimited = status['unlimited'] == true;
      final credits = status['credits'];
      setState(() => _creditLabel = unlimited || credits == null ? '' : '剩余 $credits 次');
    } catch (_) {}
  }

  Future<void> _redeem() async {
    final controller = TextEditingController();
    final code = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.canvas,
        title: const Text('兑换次数', style: AppType.title),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(hintText: '输入兑换码'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: const Text('兑换')),
        ],
      ),
    );
    controller.dispose();
    if (code == null || code.isEmpty || !mounted) return;
    try {
      final res = await _api.redeem(code);
      if (!mounted) return;
      _toast((res['message'] as String?) ?? (res['ok'] == true ? '已加上 ${res['added']} 次' : '兑换码无效'));
      await _loadCredits();
    } catch (_) {
      if (mounted) _toast('现在连不上。过一会儿再兑换。');
    }
  }

  Future<void> _loadHistory() async {
    try {
      final res = await _api.fetchHistory();
      if (!mounted) return;
      final sid = res['session_id'] as String?;
      final rawMsgs = (res['messages'] as List?) ?? const [];
      if (rawMsgs.isEmpty) return;
      final restored = <_Message>[
        _Message.assistant(const [
          {
            'type': 'text',
            'text':
                '把不会的题拍给我（电脑端可直接 Ctrl+V 粘贴截图，支持多张图配文字一起发），或直接打字提问。下方可随时打开「错题库」和「知识点库」。',
          },
        ]),
      ];
      for (final item in rawMsgs) {
        if (item is! Map) continue;
        final role = (item['role'] ?? '').toString();
        if (role == 'user') {
          final images = <Uint8List>[];
          final rawImages = item['images'];
          if (rawImages is List) {
            for (final raw in rawImages) {
              final text = raw.toString();
              if (text.isEmpty) continue;
              try {
                final payload = text.contains(',') ? text.split(',').last : text;
                images.add(base64Decode(payload));
              } catch (_) {}
            }
          }
          final shown = (item['text'] ?? '').toString().replaceFirst(RegExp(r'^\[照片(?:×\d+)?\]'), '');
          restored.add(_Message.user(shown, images: images));
        } else {
          final blocks = (item['blocks'] as List?) ?? const [];
          if (blocks.isNotEmpty) {
            restored.add(_Message.assistant(blocks.cast<Map>()));
          } else {
            restored.add(_Message.assistant([
              {'type': 'text', 'text': (item['text'] ?? '').toString()},
            ]));
          }
        }
      }
      setState(() {
        _sessionId = sid;
        _messages
          ..clear()
          ..addAll(restored);
      });
      _jump();
      await _pullTasks();
    } catch (_) {}
  }

  Future<void> _pullTasks() async {
    if (!mounted || _sending) return;
    try {
      final res = await _api.pullTasks(sessionId: _sessionId);
      if (!mounted) return;
      final sid = res['session_id'] as String?;
      final blocks = (res['blocks'] as List?) ?? const [];
      if (sid != null && sid.isNotEmpty) _sessionId = sid;
      if (blocks.isEmpty) return;
      setState(() {
        _messages.add(_Message.assistant(blocks.cast<Map>()));
      });
      _jump();
    } catch (_) {}
  }

  Future<void> _confirmClearHistory() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.canvas,
        title: const Text('清除对话历史？', style: AppType.title),
        content: const Text(
          '清除后当前页面的聊天记录会被清空（已归档进「错题库」和「知识点库」的内容仍会保留）。',
          style: AppType.body,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.error,
              foregroundColor: AppColors.onPrimary,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('确认清除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _api.clearHistory();
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _sessionId = null;
      _pendingImages.clear();
      _messages
        ..clear()
        ..add(
          _Message.assistant(const [
            {
              'type': 'text',
              'text':
                  '历史对话已清空。把不会的题拍给我（电脑端可直接 Ctrl+V 粘贴截图，支持多张图配文字一起发），或直接打字提问。',
            },
          ]),
        );
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _taskTimer?.cancel();
    _pasteListener.dispose();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(text), duration: const Duration(seconds: 2)),
    );
  }

  bool _addPending(Uint8List bytes) {
    if (!mounted || bytes.isEmpty) return false;
    if (_pendingImages.length >= maxPhotosPerSend) {
      _toast('一次最多放 3 张图。先发出去，或删掉一张再加。');
      return false;
    }
    setState(() => _pendingImages.add(bytes));
    return true;
  }

  void _stagePastedImage(Uint8List bytes) {
    if (!_addPending(bytes)) return;
    _toast('已粘贴图片到待发送区（共 ${_pendingImages.length} 张），可补充文字说明再发送');
  }

  Future<void> _pasteFromClipboardManual() async {
    final bytes = await readClipboardImageBytes();
    if (bytes != null && bytes.isNotEmpty) {
      _stagePastedImage(bytes);
      return;
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('网页端请直接按 Ctrl+V 粘贴截图；若剪贴板里没有图片，也可从相册选择。'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  void _stopSending() {
    if (!_sending) return;
    _api.cancelCurrent();
    final wake = _wake;
    if (wake != null && !wake.isCompleted) wake.complete();
    setState(() {
      _sending = false;
      _messages.add(
        _Message.assistant(const [
          {'type': 'text', 'text': '已停止本次生成。你可以补充说明或重新发送。'},
        ]),
      );
    });
    _jump();
  }

  void _showReply(Map<String, dynamic> reply) {
    final sid = reply['session_id'] as String?;
    if (sid != null && sid.isNotEmpty) _sessionId = sid;
    final blocks = (reply['blocks'] as List?) ?? const [];
    if (blocks.isEmpty || !mounted) return;
    setState(() {
      _messages.add(_Message.assistant(blocks.cast<Map>()));
    });
    _jump();
  }

  Future<void> _pauseForReply() {
    final wake = Completer<void>();
    _wake = wake;
    return Future.any([
      Future<void>.delayed(const Duration(seconds: 4)),
      wake.future,
    ]);
  }

  Future<Map<String, dynamic>?> _waitForReply(int afterId, Future<Map<String, dynamic>>? chat) async {
    final deadline = DateTime.now().add(const Duration(seconds: 170));
    Completer<Map<String, dynamic>?>? done;
    if (chat != null) {
      final box = Completer<Map<String, dynamic>?>();
      done = box;
      chat.then<void>((reply) {
        if (!box.isCompleted) box.complete(reply);
      }, onError: (Object _) {
        if (!box.isCompleted) box.complete(null);
      });
    }
    while (mounted && _sending && DateTime.now().isBefore(deadline)) {
      if (done != null && done.isCompleted) {
        final direct = await done.future;
        if (direct != null) return direct;
        done = null;
      }
      if (afterId >= 0) {
        final found = await _api.replyAfter(afterId);
        if (found != null) {
          _api.cancelCurrent();
          return found;
        }
      }
      if (!mounted || !_sending) return null;
      await _pauseForReply();
    }
    if (done != null && done.isCompleted) return done.future;
    return null;
  }

  Future<void> _catchUnfinished() async {
    if (!mounted || _sending) return;
    Map<String, dynamic> res;
    try {
      res = await _api.fetchHistory(lite: true);
    } catch (_) {
      return;
    }
    final messages = (res['messages'] as List?) ?? const [];
    if (messages.isEmpty || messages.last is! Map) return;
    final last = messages.last as Map;
    if (last['role'] != 'user') return;
    final created = DateTime.tryParse('${last['created_at']}');
    if (created == null || DateTime.now().difference(created) > const Duration(minutes: 8)) return;
    final afterId = int.tryParse('${last['id']}') ?? 0;
    if (afterId <= 0 || !mounted || _sending) return;
    setState(() => _sending = true);
    await startTeachKeepAlive();
    try {
      final reply = await _waitForReply(afterId, null);
      if (!mounted || !_sending || reply == null) return;
      _showReply(reply);
    } finally {
      if (mounted && _sending) setState(() => _sending = false);
      await stopTeachKeepAlive();
    }
  }

  Future<void> _send({String? text, List<Uint8List>? overrideImages}) async {
    final trimmed = (text ?? _input.text).trim();
    final imagesToSend = overrideImages ?? List<Uint8List>.from(_pendingImages);
    if (_sending || (trimmed.isEmpty && imagesToSend.isEmpty)) return;
    if (trimmed.length > maxQuestionChars) {
      _toast('一道题请控制在 800 字以内。题干留下即可，讲解可以下一条再问。');
      return;
    }
    if (imagesToSend.length > maxPhotosPerSend) {
      _toast('一次最多发 3 张图。请先框出要讲的那几道。');
      return;
    }
    final fitted = [for (final item in imagesToSend) fitPhotoForSend(item)];
    final totalBytes = fitted.fold<int>(0, (sum, item) => sum + item.length);
    if (fitted.any((item) => item.length > maxPhotoBytes) || totalBytes > maxPhotoTotalBytes) {
      _toast('图片还是太大。请只框一道题，或少发几张。');
      return;
    }

    setState(() {
      _sending = true;
      _retrying = false;
      if (overrideImages == null) {
        _pendingImages.clear();
      }
      _messages.add(_Message.user(trimmed, images: fitted));
    });
    if (text == null || text == _input.text) {
      _input.clear();
    }
    _jump();

    var beforeId = -1;
    try {
      beforeId = await _api.latestMessageId();
    } catch (_) {}
    final encodedList = fitted.map(base64Encode).toList();
    Future<Map<String, dynamic>> startChat() {
      return _api.chat(
        sessionId: _sessionId,
        text: trimmed,
        imageBase64: encodedList.length == 1 ? encodedList.first : null,
        imagesBase64: encodedList.isEmpty ? null : encodedList,
        onRetry: () {
          if (!mounted || !_sending) return;
          setState(() => _retrying = true);
        },
      );
    }

    await startTeachKeepAlive();
    var gotReply = false;
    try {
      final reply = await _waitForReply(beforeId, startChat());
      if (!mounted || !_sending || reply == null) {
        if (mounted && _sending) {
          setState(() {
            _messages.add(_Message.assistant(const [
              {'type': 'text', 'text': '现在连不上家教服务。过一会儿再发一次。'},
            ]));
          });
        }
        return;
      }
      gotReply = true;
      _showReply(reply);
    } finally {
      if (mounted && _sending) {
        setState(() => _sending = false);
      }
      if (!gotReply) {
        _api.cancelCurrent();
      }
      _loadCredits();
      _jump();
      await stopTeachKeepAlive();
    }
  }

  Future<void> _stageCropped(Uint8List bytes, {String? stepLabel, int? replaceAt}) async {
    if (!mounted || bytes.isEmpty) return;
    final result = await Navigator.of(context).push<Uint8List>(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => ImageCropPage(bytes: bytes, stepLabel: stepLabel),
      ),
    );
    if (result == null || !mounted) return;
    if (replaceAt != null && replaceAt >= 0 && replaceAt < _pendingImages.length) {
      setState(() => _pendingImages[replaceAt] = result);
      return;
    }
    _addPending(result);
  }

  Future<void> _pickCamera() async {
    try {
      if (_pendingImages.length >= maxPhotosPerSend) {
        _toast('一次最多放 3 张图。先发出去，或删掉一张再加。');
        return;
      }
      final file = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85, maxWidth: 1600);
      if (file == null || !mounted) return;
      final bytes = await file.readAsBytes();
      await _stageCropped(bytes);
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('没有打开相机。请允许拍照权限后再试。')),
      );
    }
  }

  Future<void> _pickGalleryMulti() async {
    List<Uint8List> loaded = [];
    try {
      if (_pendingImages.length >= maxPhotosPerSend) {
        _toast('一次最多放 3 张图。先发出去，或删掉一张再加。');
        return;
      }
      final files = await _picker.pickMultiImage(imageQuality: 85, maxWidth: 1600);
      if (files.isEmpty) return;
      for (final f in files) {
        loaded.add(await f.readAsBytes());
      }
    } catch (_) {
      try {
        final single = await _picker.pickImage(source: ImageSource.gallery, imageQuality: 85, maxWidth: 1600);
        if (single == null) return;
        loaded = [await single.readAsBytes()];
      } catch (_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('没有打开相册。请允许选图权限后再试。')),
        );
        return;
      }
    }
    if (!mounted || loaded.isEmpty) return;
    for (var i = 0; i < loaded.length; i++) {
      if (!mounted) return;
      if (_pendingImages.length >= maxPhotosPerSend) {
        _toast('一次最多放 3 张图。多出来的先不裁了。');
        break;
      }
      final label = loaded.length > 1 ? '第 ${i + 1}/${loaded.length} 张' : null;
      await _stageCropped(loaded[i], stepLabel: label);
    }
  }

  void _showPhotoOptions() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.canvas,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(12)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('拍照解题（图片先放入待发送区，可配文字说明）', style: AppType.button),
              const SizedBox(height: 8),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.camera_alt_outlined, color: AppColors.primary),
                title: const Text('拍照添加', style: AppType.body),
                subtitle: const Text('拍完可框选，也能放大后把答案涂成马赛克', style: AppType.caption),
                onTap: () {
                  Navigator.pop(ctx);
                  _pickCamera();
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.photo_library_outlined, color: AppColors.primary),
                title: const Text('从相册选图（支持多选）', style: AppType.body),
                subtitle: const Text('每张都可框选，或涂掉下划线上的答案', style: AppType.caption),
                onTap: () {
                  Navigator.pop(ctx);
                  _pickGalleryMulti();
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.content_paste_rounded, color: AppColors.primary),
                title: const Text('粘贴剪贴板截图（Ctrl+V）', style: AppType.body),
                subtitle: const Text('电脑端截图后直接按 Ctrl+V 即可粘贴到待发送区', style: AppType.caption),
                onTap: () {
                  Navigator.pop(ctx);
                  _pasteFromClipboardManual();
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _openErrorBankSheet() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.canvas,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(12)),
      ),
      builder: (ctx) => _ErrorBankSheet(
        api: _api,
        onAskInChat: (prompt) {
          Navigator.pop(ctx);
          _send(text: prompt, overrideImages: const []);
        },
      ),
    );
  }

  void _openKnowledgeBaseSheet() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.canvas,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(12)),
      ),
      builder: (ctx) => _KnowledgeBaseSheet(
        api: _api,
        gradeLabel: widget.gradeLabel,
        onAskInChat: (prompt) {
          Navigator.pop(ctx);
          _send(text: prompt, overrideImages: const []);
        },
      ),
    );
  }

  void _stageHistoryImage(Uint8List bytes) {
    if (!mounted || bytes.isEmpty || _sending) return;
    if (!_addPending(Uint8List.fromList(bytes))) return;
    _toast('这张图已放回待发送，点发送就会再讲一次。');
  }

  void _jump() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 240),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyV, control: true): () {
          readClipboardImageBytes().then((bytes) {
            if (bytes != null && bytes.isNotEmpty) {
              _stagePastedImage(bytes);
            }
          });
        },
      },
      child: Scaffold(
        backgroundColor: AppColors.surface,
        appBar: AppBar(
          backgroundColor: AppColors.canvas,
          foregroundColor: AppColors.ink,
          elevation: 0,
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('数学家教', style: AppType.title),
              GestureDetector(
                onTap: _sending ? null : widget.onChangeGrade,
                child: Text(
                  _creditLabel.isEmpty ? '${widget.gradeLabel} · 人教版' : '${widget.gradeLabel} · $_creditLabel',
                  style: AppType.caption.copyWith(color: AppColors.primary),
                ),
              ),
            ],
          ),
          actions: [
            IconButton(
              onPressed: _sending ? null : _redeem,
              icon: const Icon(Icons.confirmation_number_outlined, color: AppColors.slate),
              tooltip: '兑换次数',
            ),
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: TextButton.icon(
                onPressed: _sending ? null : _confirmClearHistory,
                icon: const Icon(Icons.delete_outline_rounded, size: 18, color: AppColors.slate),
                label: Text('清除记录', style: AppType.caption.copyWith(color: AppColors.slate)),
              ),
            ),
          ],
        ),
        body: Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                itemCount: _messages.length,
                itemBuilder: (context, index) => _Bubble(
                  message: _messages[index],
                  onAsk: (prompt) => _send(text: prompt, overrideImages: const []),
                  onReuseImage: _sending ? null : _stageHistoryImage,
                ),
              ),
            ),
            if (_sending)
              Container(
                width: double.infinity,
                color: AppColors.surfaceSoft,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.primary),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      _retrying ? '刚才没连上，正在重试一次…' : '正在讲解。可以先去看微信，讲完再回来。',
                      style: AppType.caption,
                    ),
                    const SizedBox(width: 12),
                    InkWell(
                      onTap: _stopSending,
                      child: Text(
                        '停止回答',
                        style: AppType.caption.copyWith(
                          color: AppColors.error,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            Container(
              color: AppColors.canvas,
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_pendingImages.isNotEmpty) _buildStagingTray(),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: [
                        _ActionChip(
                          icon: Icons.add_a_photo_outlined,
                          label: '拍照解题',
                          onTap: _sending ? null : _showPhotoOptions,
                        ),
                        _ActionChip(
                          icon: Icons.bookmark_border_rounded,
                          label: '错题库',
                          onTap: _sending ? null : _openErrorBankSheet,
                        ),
                        _ActionChip(
                          icon: Icons.account_tree_outlined,
                          label: '知识点库',
                          onTap: _sending ? null : _openKnowledgeBaseSheet,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      IconButton(
                        tooltip: '添加图片（支持多张）',
                        onPressed: _sending ? null : _pickGalleryMulti,
                        icon: const Icon(Icons.image_outlined, color: AppColors.slate),
                      ),
                      Expanded(
                        child: TextField(
                          controller: _input,
                          minLines: 1,
                          maxLines: 4,
                          style: AppType.body,
                          decoration: InputDecoration(
                            hintText: _pendingImages.isNotEmpty
                                ? '补充说明（如：只讲第3题 / 这两张是一道题），也可直接发送'
                                : '问一道题、说「把这题放到错题库」，或直接 Ctrl+V 粘贴截图',
                            hintStyle: AppType.body.copyWith(color: AppColors.muted),
                            filled: true,
                            fillColor: AppColors.surface,
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(color: AppColors.hairline),
                            ),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(color: AppColors.hairline),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(color: AppColors.primary),
                            ),
                          ),
                          onSubmitted: (value) {
                            if (!_sending) _send(text: value);
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                      SizedBox(
                        height: 48,
                        width: 48,
                        child: _sending
                            ? FilledButton(
                                style: FilledButton.styleFrom(
                                  backgroundColor: AppColors.error,
                                  foregroundColor: AppColors.onPrimary,
                                  padding: EdgeInsets.zero,
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                ),
                                onPressed: _stopSending,
                                child: const Tooltip(
                                  message: '停止生成',
                                  child: Icon(Icons.stop_rounded),
                                ),
                              )
                            : FilledButton(
                                style: FilledButton.styleFrom(
                                  backgroundColor: AppColors.primary,
                                  foregroundColor: AppColors.onPrimary,
                                  padding: EdgeInsets.zero,
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                ),
                                onPressed: () => _send(text: _input.text),
                                child: const Icon(Icons.arrow_upward),
                              ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStagingTray() {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: AppColors.surfaceSoft,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.hairline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '待发送图片（${_pendingImages.length} 张）· 可在下方输入说明后一起发送',
                style: AppType.caption.copyWith(color: AppColors.charcoal, fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              InkWell(
                onTap: () => setState(() => _pendingImages.clear()),
                child: Text('清空', style: AppType.caption.copyWith(color: AppColors.error)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (var i = 0; i < _pendingImages.length; i++)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Stack(
                      children: [
                        GestureDetector(
                          onTap: () => _openImage(context, _pendingImages[i]),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(8),
                            child: Container(
                              color: AppColors.canvas,
                              child: Image.memory(
                                _pendingImages[i],
                                width: 76,
                                height: 76,
                                fit: BoxFit.cover,
                              ),
                            ),
                          ),
                        ),
                        Positioned(
                          left: 4,
                          bottom: 4,
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                            decoration: BoxDecoration(
                              color: AppColors.ink.withOpacity(0.72),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              '图${i + 1}',
                              style: AppType.caption.copyWith(color: AppColors.onPrimary, fontSize: 10),
                            ),
                          ),
                        ),
                        Positioned(
                          right: 2,
                          bottom: 2,
                          child: InkWell(
                            onTap: () => _stageCropped(_pendingImages[i], replaceAt: i),
                            child: Container(
                              padding: const EdgeInsets.all(2),
                              decoration: const BoxDecoration(
                                color: AppColors.primary,
                                shape: BoxShape.circle,
                              ),
                              child: const Icon(Icons.crop, size: 13, color: AppColors.onPrimary),
                            ),
                          ),
                        ),
                        Positioned(
                          right: 2,
                          top: 2,
                          child: InkWell(
                            onTap: () => setState(() => _pendingImages.removeAt(i)),
                            child: Container(
                              padding: const EdgeInsets.all(2),
                              decoration: const BoxDecoration(
                                color: AppColors.ink,
                                shape: BoxShape.circle,
                              ),
                              child: const Icon(Icons.close, size: 13, color: AppColors.onPrimary),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                InkWell(
                  onTap: _pickGalleryMulti,
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    width: 76,
                    height: 76,
                    decoration: BoxDecoration(
                      color: AppColors.canvas,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: AppColors.hairlineStrong),
                    ),
                    child: const Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.add, color: AppColors.slate, size: 22),
                        SizedBox(height: 2),
                        Text('加一张', style: AppType.caption),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ActionChip extends StatelessWidget {
  const _ActionChip({required this.icon, required this.label, required this.onTap});

  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: OutlinedButton.icon(
        onPressed: onTap,
        icon: Icon(icon, size: 16, color: AppColors.primary),
        label: Text(label),
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.ink,
          side: const BorderSide(color: AppColors.hairlineStrong),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          textStyle: AppType.button,
        ),
      ),
    );
  }
}

class _Message {
  _Message.user(this.text, {List<Uint8List>? images})
      : fromUser = true,
        images = images ?? const [],
        blocks = const [];

  _Message.assistant(List<Map> raw)
      : fromUser = false,
        text = '',
        images = const [],
        blocks = raw.map((item) => Map<String, dynamic>.from(item)).toList();

  final bool fromUser;
  final String text;
  final List<Uint8List> images;
  final List<Map<String, dynamic>> blocks;
}

void _openImage(BuildContext context, Uint8List bytes, {VoidCallback? onReuse}) {
  showDialog<void>(
    context: context,
    builder: (dialogContext) {
      final height = MediaQuery.sizeOf(dialogContext).height * 0.7;
      return Dialog(
        backgroundColor: AppColors.canvas,
        insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Align(
              alignment: Alignment.centerRight,
              child: IconButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                icon: const Icon(Icons.close, color: AppColors.ink),
              ),
            ),
            SizedBox(
              height: height,
              width: double.infinity,
              child: InteractiveViewer(
                minScale: 1,
                maxScale: 5,
                child: Image.memory(bytes, fit: BoxFit.contain),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
              child: Row(
                children: [
                  const Expanded(
                    child: Text('双指或鼠标滚轮可以缩放查看细节', style: AppType.caption),
                  ),
                  if (onReuse != null)
                    TextButton(
                      onPressed: () {
                        Navigator.of(dialogContext).pop();
                        onReuse();
                      },
                      child: Text(
                        '再发一次',
                        style: AppType.button.copyWith(color: AppColors.primary),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      );
    },
  );
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message, required this.onAsk, this.onReuseImage});

  final _Message message;
  final ValueChanged<String> onAsk;
  final ValueChanged<Uint8List>? onReuseImage;

  @override
  Widget build(BuildContext context) {
    final user = message.fromUser;
    return Align(
      alignment: user ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.88),
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: user ? AppColors.lavender : AppColors.canvas,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: user ? AppColors.lavender : AppColors.hairline),
        ),
        child: user ? _userBody(context) : _assistantBody(),
      ),
    );
  }

  Widget _userBody(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (message.images.isNotEmpty)
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (var i = 0; i < message.images.length; i++)
                MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      GestureDetector(
                        onTap: () => _openImage(
                          context,
                          message.images[i],
                          onReuse: onReuseImage == null ? null : () => onReuseImage!(message.images[i]),
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: Image.memory(
                            message.images[i],
                            height: message.images.length > 1 ? 130 : 180,
                            fit: BoxFit.contain,
                          ),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Wrap(
                        spacing: 10,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          Text(
                            message.images.length > 1 ? '图${i + 1} · 点开放大' : '点开放大',
                            style: AppType.caption,
                          ),
                          if (onReuseImage != null)
                            GestureDetector(
                              onTap: () => onReuseImage!(message.images[i]),
                              child: Text(
                                '再发一次',
                                style: AppType.caption.copyWith(
                                  color: AppColors.primary,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
            ],
          ),
        if (message.text.isNotEmpty)
          Padding(
            padding: EdgeInsets.only(top: message.images.isEmpty ? 0 : 8),
            child: SelectableText(message.text, style: AppType.body),
          ),
      ],
    );
  }

  Widget _assistantBody() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final block in message.blocks) ...[
          _block(block),
          const SizedBox(height: 8),
        ],
      ],
    );
  }

  Widget _block(Map<String, dynamic> block) {
    switch (block['type']) {
      case 'figure':
        final figure = block['figure'];
        if (figure is! Map) return const SizedBox.shrink();
        return FigureView(
          figure: Map<String, dynamic>.from(figure),
          caption: block['caption'] as String?,
        );
      case 'knowledge_card':
        final card = block['card'];
        if (card is! Map) return const SizedBox.shrink();
        return _KnowledgeCardView(
          card: Map<String, dynamic>.from(card),
          onAsk: onAsk,
        );
      case 'tree':
        return _Tree(chapters: (block['chapters'] as List?) ?? const [], onAsk: onAsk);
      case 'errors':
        return _Errors(items: (block['items'] as List?) ?? const [], onAsk: onAsk);
      default:
        return SelectableText((block['text'] ?? '').toString(), style: AppType.body);
    }
  }
}

class _HighlightText extends StatelessWidget {
  const _HighlightText(
    this.text, {
    required this.style,
    this.query = '',
    this.maxLines,
    this.overflow,
  });

  final String text;
  final TextStyle style;
  final String query;
  final int? maxLines;
  final TextOverflow? overflow;

  @override
  Widget build(BuildContext context) {
    final q = query.trim();
    if (q.isEmpty) {
      return Text(text, style: style, maxLines: maxLines, overflow: overflow);
    }
    final lowerText = text.toLowerCase();
    final lowerQ = q.toLowerCase();
    final spans = <TextSpan>[];
    var start = 0;
    while (true) {
      final idx = lowerText.indexOf(lowerQ, start);
      if (idx < 0) {
        if (start < text.length) {
          spans.add(TextSpan(text: text.substring(start), style: style));
        }
        break;
      }
      if (idx > start) {
        spans.add(TextSpan(text: text.substring(start, idx), style: style));
      }
      spans.add(
        TextSpan(
          text: text.substring(idx, idx + q.length),
          style: style.copyWith(
            backgroundColor: AppColors.lavender,
            color: AppColors.primary,
            fontWeight: FontWeight.w700,
          ),
        ),
      );
      start = idx + q.length;
    }
    return RichText(
      maxLines: maxLines,
      overflow: overflow ?? TextOverflow.clip,
      text: TextSpan(children: spans),
    );
  }
}

class _KnowledgeCardView extends StatelessWidget {
  const _KnowledgeCardView({
    required this.card,
    required this.onAsk,
    this.highlightQuery = '',
  });

  final Map<String, dynamic> card;
  final ValueChanged<String> onAsk;
  final String highlightQuery;

  @override
  Widget build(BuildContext context) {
    final title = (card['title'] ?? '').toString();
    final volume = (card['volume'] ?? '').toString();
    final tags = (card['tags'] ?? '').toString();
    final summary = (card['summary'] ?? '').toString();
    final example = (card['example'] ?? '').toString();
    final mindmap = (card['mindmap'] as List?)?.map((e) => e.toString()).toList() ?? const <String>[];

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surfaceSoft,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.hairlineStrong),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.lavender,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  volume.isEmpty ? '知识点卡' : volume,
                  style: AppType.caption.copyWith(color: AppColors.primary, fontWeight: FontWeight.w600),
                ),
              ),
              if (tags.isNotEmpty) ...[
                const SizedBox(width: 8),
                Expanded(
                  child: _HighlightText(
                    tags,
                    query: highlightQuery,
                    style: AppType.caption,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 6),
          _HighlightText(
            title,
            query: highlightQuery,
            style: AppType.title.copyWith(fontSize: 16),
          ),
          const SizedBox(height: 6),
          _HighlightText(
            summary,
            query: highlightQuery,
            style: AppType.body,
          ),
          if (mindmap.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text('思维导图 / 核心脉络：', style: AppType.button.copyWith(color: AppColors.primary)),
            const SizedBox(height: 6),
            for (var i = 0; i < mindmap.length; i++)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 20,
                      height: 20,
                      alignment: Alignment.center,
                      margin: const EdgeInsets.only(top: 2, right: 8),
                      decoration: BoxDecoration(
                        color: AppColors.lavender,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        '${i + 1}',
                        style: AppType.caption.copyWith(color: AppColors.primary, fontWeight: FontWeight.w600),
                      ),
                    ),
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                        decoration: BoxDecoration(
                          color: AppColors.canvas,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: AppColors.hairline),
                        ),
                        child: _HighlightText(
                          mindmap[i],
                          query: highlightQuery,
                          style: AppType.small,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
          if (example.isNotEmpty) ...[
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppColors.canvas,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.hairline),
              ),
              child: _HighlightText(
                example,
                query: highlightQuery,
                style: AppType.small,
              ),
            ),
          ],
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              OutlinedButton(
                onPressed: () => onAsk('围绕「$title」给我出一道典型例题并讲透'),
                child: const Text('看典型例题'),
              ),
              OutlinedButton(
                onPressed: () => onAsk('再来一道「$title」的练习题'),
                child: const Text('练一道题'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Tree extends StatelessWidget {
  const _Tree({required this.chapters, required this.onAsk});

  final List chapters;
  final ValueChanged<String> onAsk;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final raw in chapters)
          if (raw is Map) _chapter(Map<String, dynamic>.from(raw)),
      ],
    );
  }

  Widget _chapter(Map<String, dynamic> chapter) {
    final locked = chapter['status'] == 'locked';
    final children = (chapter['children'] as List?) ?? const [];
    final vol = (chapter['volume'] ?? '').toString();
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => onAsk('讲讲${chapter['title']}'),
            child: Text(
              vol.isNotEmpty ? '$vol · ${chapter['title']}' : (chapter['title']?.toString() ?? ''),
              style: AppType.button.copyWith(color: locked ? AppColors.stone : AppColors.charcoal),
            ),
          ),
          if (!locked)
            for (final raw in children)
              if (raw is Map)
                InkWell(
                  onTap: () => onAsk('讲讲${raw['title']}'),
                  child: Padding(
                    padding: const EdgeInsets.only(left: 8, top: 6),
                    child: Row(
                      children: [
                        _Dot(status: raw['status']?.toString() ?? 'new'),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            raw['title']?.toString() ?? '',
                            style: AppType.small.copyWith(color: AppColors.ink),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
        ],
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      'shaky' => AppColors.warning,
      'ok' => AppColors.success,
      _ => AppColors.slate,
    };
    return Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle));
  }
}

class _Errors extends StatelessWidget {
  const _Errors({required this.items, required this.onAsk});

  final List items;
  final ValueChanged<String> onAsk;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (final raw in items)
          if (raw is Map) _ErrorItemCard(item: Map<String, dynamic>.from(raw), onAsk: onAsk),
      ],
    );
  }
}

class _ErrorItemCard extends StatefulWidget {
  const _ErrorItemCard({required this.item, required this.onAsk, this.onDelete});

  final Map<String, dynamic> item;
  final ValueChanged<String> onAsk;
  final Future<void> Function(int id)? onDelete;

  @override
  State<_ErrorItemCard> createState() => _ErrorItemCardState();
}

class _ErrorItemCardState extends State<_ErrorItemCard> {
  bool _expanded = false;

  List<Uint8List> _errorImages(Map<String, dynamic> item) {
    final raw = item['images'];
    if (raw is! List) return const [];
    final out = <Uint8List>[];
    for (final piece in raw) {
      final text = piece.toString().trim();
      if (text.isEmpty) continue;
      try {
        out.add(base64Decode(text.contains(',') ? text.split(',').last : text));
      } catch (_) {}
    }
    return out;
  }

  Future<void> _confirmDelete(String stem) async {
    final id = int.tryParse('${widget.item['id']}');
    if (id == null) return;
    final short = stem.length > 36 ? '${stem.substring(0, 36)}…' : stem;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.canvas,
        title: const Text('从错题库拿掉', style: AppType.title),
        content: Text('这道题会从错题库删除。\n$short', style: AppType.body),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text('删除', style: AppType.button.copyWith(color: AppColors.error)),
          ),
        ],
      ),
    );
    if (ok == true) await widget.onDelete?.call(id);
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final chTitle = (item['chapter_title'] ?? '').toString();
    final nodeTitle = (item['node_title'] ?? '').toString();
    final errLabel = (item['error_label'] ?? '').toString();
    final srcLabel = (item['source_label'] ?? '错题记录').toString();
    final stem = (item['stem'] ?? '').toString();
    final expected = (item['expected'] ?? '').toString();
    final studentAns = (item['student_answer'] ?? '').toString();
    final solution = (item['solution'] ?? item['summary'] ?? '').toString();

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.surfaceSoft,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.hairline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: [
              if (chTitle.isNotEmpty)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.lavender,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(chTitle, style: AppType.caption.copyWith(color: AppColors.primary)),
                ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.canvas,
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: AppColors.hairlineStrong),
                ),
                child: Text(srcLabel, style: AppType.caption),
              ),
              Text(
                '$nodeTitle · $errLabel',
                style: AppType.button.copyWith(color: AppColors.warning),
              ),
            ],
          ),
          const SizedBox(height: 6),
          if (_errorImages(item).isNotEmpty) ...[
            for (final bytes in _errorImages(item))
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: Image.memory(bytes, height: 180, fit: BoxFit.contain),
                ),
              ),
            Text('原题图片', style: AppType.caption),
            const SizedBox(height: 6),
          ],
          SelectableText('【题干】$stem', style: AppType.body),
          if (studentAns.isNotEmpty || expected.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              '${studentAns.isNotEmpty ? "当时错填：$studentAns    " : ""}${expected.isNotEmpty ? "标准结果：$expected" : ""}',
              style: AppType.caption.copyWith(color: AppColors.charcoal),
            ),
          ],
          if (_expanded && solution.isNotEmpty) ...[
            const Divider(height: 16, color: AppColors.hairline),
            SelectableText('【完整解析过程】\n$solution', style: AppType.small),
          ],
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            children: [
              TextButton(
                onPressed: () => setState(() => _expanded = !_expanded),
                child: Text(_expanded ? '收起解析' : '查看完整解析'),
              ),
              TextButton(
                onPressed: () => widget.onAsk('请重新详细讲一下这道错题：$stem'),
                child: const Text('在对话中重讲'),
              ),
              TextButton(
                onPressed: () => widget.onAsk('针对这道错题「$stem」，帮我出一道同型变式题练练'),
                child: const Text('练一道同型题'),
              ),
              if (widget.onDelete != null)
                TextButton(
                  onPressed: () => _confirmDelete(stem),
                  child: Text('已掌握，删除', style: AppType.button.copyWith(color: AppColors.error)),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ErrorBankSheet extends StatefulWidget {
  const _ErrorBankSheet({required this.api, required this.onAskInChat});

  final TutorApi api;
  final ValueChanged<String> onAskInChat;

  @override
  State<_ErrorBankSheet> createState() => _ErrorBankSheetState();
}

class _ErrorBankSheetState extends State<_ErrorBankSheet> {
  bool _loading = true;
  String _selectedChapter = '';
  Map<String, dynamic> _data = const {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final res = await widget.api.fetchErrors(chapterId: _selectedChapter);
      if (!mounted) return;
      setState(() {
        _data = res;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  Future<void> _delete(int errorId) async {
    try {
      final ok = await widget.api.deleteError(errorId);
      if (!mounted) return;
      if (ok) await _load();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final chapters = (_data['chapters'] as List?) ?? const [];
    final items = (_data['items'] as List?) ?? const [];

    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.82,
      minChildSize: 0.5,
      maxChildSize: 0.94,
      builder: (context, scrollController) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('历史错题库（按人教版章节归档）', style: AppType.title),
                        Text('收录标准：①卷面错题/红叉 ②练习做错 ③高频追问 ④对话中说「放到错题库」', style: AppType.caption),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              if (chapters.isNotEmpty)
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: ChoiceChip(
                          label: const Text('全部章节'),
                          selected: _selectedChapter.isEmpty,
                          onSelected: (_) {
                            setState(() => _selectedChapter = '');
                            _load();
                          },
                        ),
                      ),
                      for (final ch in chapters)
                        if (ch is Map)
                          Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: ChoiceChip(
                              label: Text('${ch['chapter_title']} (${ch['count']})'),
                              selected: _selectedChapter == ch['chapter_id'],
                              onSelected: (_) {
                                setState(() => _selectedChapter = ch['chapter_id'].toString());
                                _load();
                              },
                            ),
                          ),
                    ],
                  ),
                ),
              const SizedBox(height: 8),
              Expanded(
                child: _loading
                    ? const Center(child: CircularProgressIndicator())
                    : items.isEmpty
                        ? Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Text(
                                  '当前还没有错题记录。\n平时拍卷子上的错题，或在对话里说「把这题放到错题库」，都会自动按课本章节存进来。',
                                  textAlign: TextAlign.center,
                                  style: AppType.body,
                                ),
                                const SizedBox(height: 12),
                                OutlinedButton(
                                  onPressed: () => widget.onAskInChat('翻翻错题'),
                                  child: const Text('在对话框查看'),
                                ),
                              ],
                            ),
                          )
                        : ListView.builder(
                            controller: scrollController,
                            itemCount: items.length,
                            itemBuilder: (ctx, i) {
                              final raw = items[i];
                              if (raw is! Map) return const SizedBox.shrink();
                              return _ErrorItemCard(
                                item: Map<String, dynamic>.from(raw),
                                onAsk: widget.onAskInChat,
                                onDelete: _delete,
                              );
                            },
                          ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _KnowledgeBaseSheet extends StatefulWidget {
  const _KnowledgeBaseSheet({required this.api, required this.onAskInChat, this.gradeLabel = '初一'});

  final TutorApi api;
  final ValueChanged<String> onAskInChat;
  final String gradeLabel;

  @override
  State<_KnowledgeBaseSheet> createState() => _KnowledgeBaseSheetState();
}

class _KnowledgeBaseSheetState extends State<_KnowledgeBaseSheet> {
  final _searchCtrl = TextEditingController();
  bool _loading = true;
  String _selectedVolume = '全部';
  Map<String, dynamic> _data = const {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  List<String> _volumeChoices(List<dynamic> chapters) {
    final volumes = <String>['全部'];
    for (final raw in chapters) {
      if (raw is! Map) continue;
      final volume = (raw['volume'] ?? '').toString();
      if (volume.isNotEmpty && !volumes.contains(volume)) volumes.add(volume);
    }
    return volumes;
  }

  Future<void> _load({String query = ''}) async {
    setState(() => _loading = true);
    try {
      final res = await widget.api.fetchKnowledge(query: query);
      if (!mounted) return;
      setState(() {
        _data = res;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final allChapters = (_data['chapters'] as List?) ?? const [];
    bool matchesVolume(Object? raw) {
      if (_selectedVolume == '全部') return true;
      return raw is Map && raw['volume'] == _selectedVolume;
    }

    final chapters = allChapters.where(matchesVolume).toList();
    final dynamicCards = ((_data['dynamic_cards'] as List?) ?? const []).where(matchesVolume).toList();
    final matchedNodes = ((_data['matched_nodes'] as List?) ?? const []).where(matchesVolume).toList();
    final qText = _searchCtrl.text.trim();

    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.86,
      minChildSize: 0.55,
      maxChildSize: 0.95,
      builder: (context, scrollController) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('人教版${widget.gradeLabel}数学 · 知识点与思维导图库', style: AppType.title),
                        Text('小学到九年级的卡片都在这里。讲题按${widget.gradeLabel}的方法。', style: AppType.caption),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _searchCtrl,
                      style: AppType.body,
                      decoration: InputDecoration(
                        hintText: '搜索知识点（如：数轴、绝对值、无理数、二元一次方程组、勾股定理）',
                        hintStyle: AppType.small.copyWith(color: AppColors.muted),
                        prefixIcon: const Icon(Icons.search, color: AppColors.slate),
                        suffixIcon: qText.isEmpty
                            ? null
                            : IconButton(
                                icon: const Icon(Icons.clear, size: 18),
                                onPressed: () {
                                  _searchCtrl.clear();
                                  _load(query: '');
                                },
                              ),
                        filled: true,
                        fillColor: AppColors.surface,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                          borderSide: const BorderSide(color: AppColors.hairline),
                        ),
                      ),
                      onSubmitted: (v) => _load(query: v),
                      onChanged: (v) {
                        if (v.trim().isEmpty) _load(query: '');
                      },
                    ),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton(
                    onPressed: () => _load(query: _searchCtrl.text),
                    child: const Text('搜索'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final vol in _volumeChoices(allChapters))
                    ChoiceChip(
                      label: Text(vol),
                      selected: _selectedVolume == vol,
                      onSelected: (_) => setState(() => _selectedVolume = vol),
                    ),
                  if (qText.isNotEmpty)
                    OutlinedButton.icon(
                      onPressed: () => widget.onAskInChat('请系统讲讲「$qText」，并整理成思维导图卡片存入知识点库'),
                      icon: const Icon(Icons.auto_awesome_outlined, size: 16),
                      label: Text('让老师整理「$qText」存入库中'),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              Expanded(
                child: _loading
                    ? const Center(child: CircularProgressIndicator())
                    : ListView(
                        controller: scrollController,
                        children: [
                          if (qText.isNotEmpty && matchedNodes.isNotEmpty) ...[
                            Text(
                              '课本精准匹配小节（${matchedNodes.length}）',
                              style: AppType.button.copyWith(color: AppColors.primary),
                            ),
                            const SizedBox(height: 6),
                            for (final raw in matchedNodes)
                              if (raw is Map)
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 10),
                                  child: _KnowledgeCardView(
                                    card: Map<String, dynamic>.from(raw),
                                    onAsk: widget.onAskInChat,
                                    highlightQuery: qText,
                                  ),
                                ),
                            const Divider(height: 20, color: AppColors.hairline),
                          ],
                          for (var i = 0; i < chapters.length; i++)
                            if (chapters[i] is Map)
                              _buildChapterSection(
                                Map<String, dynamic>.from(chapters[i] as Map),
                                qText,
                                expand: qText.isNotEmpty ||
                                    (_selectedVolume != '全部' && i == 0) ||
                                    (_selectedVolume == '全部' && (chapters[i] as Map)['id'] == 'ch1'),
                              ),
                          if (dynamicCards.isNotEmpty) ...[
                            Text(
                              '对话动态沉淀专题（${dynamicCards.length}）',
                              style: AppType.button.copyWith(color: AppColors.primary),
                            ),
                            const SizedBox(height: 6),
                            for (final raw in dynamicCards)
                              if (raw is Map)
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 10),
                                  child: _KnowledgeCardView(
                                    card: Map<String, dynamic>.from(raw),
                                    onAsk: widget.onAskInChat,
                                    highlightQuery: qText,
                                  ),
                                ),
                          ],
                          if (chapters.isEmpty && dynamicCards.isEmpty && qText.isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 32),
                              child: Center(
                                child: Column(
                                  children: [
                                    Text('课本库中暂未搜到「$qText」', style: AppType.body),
                                    const SizedBox(height: 10),
                                    FilledButton(
                                      style: FilledButton.styleFrom(
                                        backgroundColor: AppColors.primary,
                                        foregroundColor: AppColors.onPrimary,
                                      ),
                                      onPressed: () =>
                                          widget.onAskInChat('请系统讲讲「$qText」，并整理成思维导图卡片存入知识点库'),
                                      child: Text('让老师讲解「$qText」并自动存入知识点库'),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                        ],
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildChapterSection(Map<String, dynamic> ch, String qText, {bool expand = false}) {
    final vol = (ch['volume'] ?? '').toString();
    final title = (ch['title'] ?? '').toString();
    final intro = (ch['intro'] ?? '').toString();
    final mindmap = (ch['mindmap'] as List?)?.map((e) => e.toString()).toList() ?? const <String>[];
    final nodes = (ch['nodes'] as List?) ?? const [];

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: AppColors.surfaceSoft,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.hairline),
      ),
      child: ExpansionTile(
        key: ValueKey('${ch['id']}-$expand'),
        initiallyExpanded: expand,
        title: _HighlightText('$vol · $title', query: qText, style: AppType.button),
        subtitle: _HighlightText(
          intro,
          query: qText,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: AppType.caption,
        ),
        childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        children: [
          if (mindmap.isNotEmpty) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              margin: const EdgeInsets.only(bottom: 10),
              decoration: BoxDecoration(
                color: AppColors.canvas,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.hairlineStrong),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text('本章知识结构导图（教材小结）', style: AppType.button.copyWith(color: AppColors.primary)),
                      const Spacer(),
                      InkWell(
                        onTap: () => widget.onAskInChat('讲讲$title'),
                        child: Text('全章串讲 →', style: AppType.caption.copyWith(color: AppColors.primary)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  for (final line in mindmap)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: _HighlightText('• $line', query: qText, style: AppType.small),
                    ),
                ],
              ),
            ),
          ],
          for (final rawNode in nodes)
            if (rawNode is Map)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: _KnowledgeCardView(
                  card: Map<String, dynamic>.from(rawNode),
                  onAsk: widget.onAskInChat,
                  highlightQuery: qText,
                ),
              ),
        ],
      ),
    );
  }
}
