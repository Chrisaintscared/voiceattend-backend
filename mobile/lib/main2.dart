/// VoiceAttend AI – Flutter Mobile App
/// ======================================
/// Entry point. Configures the app theme and launches [HomeScreen].
library;

import 'package:flutter/material.dart';
import 'screens/home_screen.dart';
import 'screens/logs_screen.dart';

void main() {
  runApp(const VoiceAttendApp());
}

class VoiceAttendApp extends StatelessWidget {
  const VoiceAttendApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VoiceAttend AI',
      debugShowCheckedModeBanner: false,

      // ----------------------------------------------------------------
      // Theme – deep navy / teal / white palette
      // ----------------------------------------------------------------
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0A2342), // Deep navy
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: const Color(0xFF0A1628),
        fontFamily: 'Roboto',
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF00C9A7), // Teal accent
            foregroundColor: Colors.black,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
            textStyle: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
            ),
          ),
        ),
        // CardTheme was renamed to CardThemeData in Flutter 3.19+
        cardTheme: CardThemeData(
          color: const Color(0xFF132237),
          elevation: 4,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
      ),

      // ----------------------------------------------------------------
      // Named Routes
      // ----------------------------------------------------------------
      initialRoute: '/',
      routes: {
        '/': (_) => const HomeScreen(),
        '/logs': (_) => const LogsScreen(),
      },
    );
  }
}
