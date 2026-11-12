class GradeChoice {
  const GradeChoice({
    required this.id,
    required this.label,
    required this.stage,
    required this.ready,
  });

  final String id;
  final String label;
  final String stage;
  final bool ready;
}

const gradeChoices = <GradeChoice>[
  GradeChoice(id: 'p1', label: '一年级', stage: '小学', ready: true),
  GradeChoice(id: 'p2', label: '二年级', stage: '小学', ready: true),
  GradeChoice(id: 'p3', label: '三年级', stage: '小学', ready: true),
  GradeChoice(id: 'p4', label: '四年级', stage: '小学', ready: true),
  GradeChoice(id: 'p5', label: '五年级', stage: '小学', ready: true),
  GradeChoice(id: 'p6', label: '六年级', stage: '小学', ready: true),
  GradeChoice(id: 'j1', label: '初一', stage: '初中', ready: true),
  GradeChoice(id: 'j2', label: '初二', stage: '初中', ready: true),
  GradeChoice(id: 'j3', label: '初三', stage: '初中', ready: true),
];

const readyGradeId = 'j1';

GradeChoice gradeById(String? id) {
  for (final grade in gradeChoices) {
    if (grade.id == id && grade.ready) return grade;
  }
  return gradeChoices.firstWhere((grade) => grade.id == readyGradeId);
}

List<GradeChoice> gradesIn(String stage) {
  return gradeChoices.where((grade) => grade.stage == stage).toList();
}
