import 'package:flutter/material.dart';

/// 色名与字号来自项目根目录 DESIGN.md（Notion），不另加强调色。
class AppColors {
  static const primary = Color(0xFF5645D4);
  static const primaryPressed = Color(0xFF4534B3);
  static const onPrimary = Color(0xFFFFFFFF);
  static const canvas = Color(0xFFFFFFFF);
  static const surface = Color(0xFFF6F5F4);
  static const surfaceSoft = Color(0xFFFAFAF9);
  static const hairline = Color(0xFFE5E3DF);
  static const hairlineStrong = Color(0xFFC8C4BE);
  static const ink = Color(0xFF1A1A1A);
  static const charcoal = Color(0xFF37352F);
  static const slate = Color(0xFF5D5B54);
  static const stone = Color(0xFFA4A097);
  static const muted = Color(0xFFBBB8B1);
  static const success = Color(0xFF1AAE39);
  static const warning = Color(0xFFDD5B00);
  static const error = Color(0xFFE03131);
  static const lavender = Color(0xFFE6E0F5);
  static const sky = Color(0xFFDCECFA);
}

class AppType {
  static const title = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    height: 1.4,
    color: AppColors.ink,
  );
  static const body = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w400,
    height: 1.55,
    color: AppColors.ink,
  );
  static const bodyMedium = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w500,
    height: 1.55,
    color: AppColors.ink,
  );
  static const small = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    height: 1.5,
    color: AppColors.slate,
  );
  static const caption = TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w400,
    height: 1.4,
    color: AppColors.slate,
  );
  static const button = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w500,
    height: 1.3,
    color: AppColors.ink,
  );
}

ThemeData buildTheme() {
  return ThemeData(
    useMaterial3: true,
    scaffoldBackgroundColor: AppColors.surface,
    colorScheme: const ColorScheme.light(
      primary: AppColors.primary,
      onPrimary: AppColors.onPrimary,
      surface: AppColors.canvas,
      onSurface: AppColors.ink,
      error: AppColors.error,
    ),
    dividerColor: AppColors.hairline,
    splashColor: AppColors.lavender,
    textTheme: const TextTheme(
      titleMedium: AppType.title,
      bodyMedium: AppType.body,
      bodySmall: AppType.small,
      labelLarge: AppType.button,
    ),
  );
}
