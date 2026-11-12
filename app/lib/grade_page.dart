import 'package:flutter/material.dart';

import 'grades.dart';
import 'theme.dart';

class GradePage extends StatefulWidget {
  const GradePage({super.key, required this.onPicked, this.selectedId});

  final ValueChanged<String> onPicked;
  final String? selectedId;

  @override
  State<GradePage> createState() => _GradePageState();
}

class _GradePageState extends State<GradePage> {
  late String _selectedId = gradeById(widget.selectedId).id;
  String? _notice;

  void _tap(GradeChoice grade) {
    if (!grade.ready) {
      setState(() => _notice = '${grade.label}的课本还没放进来，现在先用初一。');
      return;
    }
    setState(() {
      _selectedId = grade.id;
      _notice = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final selected = gradeById(_selectedId);
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 28, 20, 24),
          child: Column(
          children: [
            Center(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(20),
                child: Image.asset('assets/icon.png', width: 84, height: 84, fit: BoxFit.cover),
              ),
            ),
            const SizedBox(height: 16),
            const Text('先选现在学到哪一册', textAlign: TextAlign.center, style: AppType.title),
            const SizedBox(height: 8),
            const Text(
              '老师按这一册的讲法来。小学一年级到初三都可以选。',
              textAlign: TextAlign.center,
              style: AppType.caption,
            ),
            const SizedBox(height: 24),
            _StageCard(
              title: '小学',
              grades: gradesIn('小学'),
              selectedId: _selectedId,
              onTap: _tap,
            ),
            const SizedBox(height: 12),
            _StageCard(
              title: '初中',
              grades: gradesIn('初中'),
              selectedId: _selectedId,
              onTap: _tap,
            ),
            if (_notice != null) ...[
              const SizedBox(height: 12),
              Text(_notice!, textAlign: TextAlign.center, style: AppType.caption.copyWith(color: AppColors.warning)),
            ],
            const SizedBox(height: 24),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: AppColors.onPrimary,
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              onPressed: () => widget.onPicked(selected.id),
              child: Text('进入${selected.label}', style: AppType.button.copyWith(color: AppColors.onPrimary)),
            ),
          ],
        ),
        ),
      ),
    );
  }
}

class _StageCard extends StatelessWidget {
  const _StageCard({
    required this.title,
    required this.grades,
    required this.selectedId,
    required this.onTap,
  });

  final String title;
  final List<GradeChoice> grades;
  final String selectedId;
  final ValueChanged<GradeChoice> onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      decoration: BoxDecoration(
        color: AppColors.canvas,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.hairline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: AppType.bodyMedium),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final grade in grades)
                _GradeChip(
                  key: ValueKey(grade.id),
                  grade: grade,
                  selected: grade.id == selectedId,
                  onTap: () => onTap(grade),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _GradeChip extends StatelessWidget {
  const _GradeChip({super.key, required this.grade, required this.selected, required this.onTap});

  final GradeChoice grade;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final background = selected ? AppColors.primary : AppColors.surface;
    final foreground = selected ? AppColors.onPrimary : (grade.ready ? AppColors.ink : AppColors.stone);
    return Material(
      color: background,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: selected ? AppColors.primary : AppColors.hairline),
          ),
          child: Text(
            grade.ready ? grade.label : '${grade.label} · 准备中',
            style: AppType.caption.copyWith(color: foreground, fontWeight: FontWeight.w600),
          ),
        ),
      ),
    );
  }
}
