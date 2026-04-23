// lib/main.dart
// App entry point — deep navy/teal theme, named routes, role-based redirect.

import 'package:flutter/material.dart';
import 'screens/login_screen.dart';
import 'screens/register_screen.dart';
import 'screens/home_screen.dart';
import 'screens/logs_screen.dart';
import 'screens/admin_screen.dart';
import 'services/auth_service.dart';

void main() => runApp(const VoiceAttendApp());

class VoiceAttendApp extends StatelessWidget {
  const VoiceAttendApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VoiceAttend AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0F6E56),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0D1B2A),
          foregroundColor: Colors.white,
          elevation: 0,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF1D9E75),
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      ),
      home: const _SplashRouter(),
      routes: {
        '/login':    (_) => const LoginScreen(),
        '/register': (_) => const RegisterScreen(),
        '/home':     (_) => const HomeScreen(),
        '/logs':     (_) => const LogsScreen(),
        '/admin':    (_) => const AdminScreen(),
      },
    );
  }
}

/// On app start, check stored JWT and route to the correct screen.
class _SplashRouter extends StatefulWidget {
  const _SplashRouter();

  @override
  State<_SplashRouter> createState() => _SplashRouterState();
}

class _SplashRouterState extends State<_SplashRouter> {
  @override
  void initState() {
    super.initState();
    _redirect();
  }

  Future<void> _redirect() async {
    await Future.delayed(const Duration(milliseconds: 300));
    final user = await AuthService.getStoredUser();
    if (!mounted) return;

    if (user == null) {
      Navigator.pushReplacementNamed(context, '/login');
    } else if (user['role'] == 'admin') {
      Navigator.pushReplacementNamed(context, '/admin');
    } else {
      Navigator.pushReplacementNamed(context, '/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF0D1B2A),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.spatial_audio_off, size: 72, color: Colors.teal),
            SizedBox(height: 16),
            Text(
              'VoiceAttend AI',
              style: TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
