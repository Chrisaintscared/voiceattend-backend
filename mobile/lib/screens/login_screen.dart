// lib/screens/login_screen.dart
import 'dart:io';
import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../services/audio_recorder_service.dart';
import 'register_screen.dart'; // ✅ IMPORTANT

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();

  final _recorder = AudioRecorderService();

  bool _isRecording = false;
  bool _isLoading = false;

  String? _voicePath;

  // ─── PASSWORD LOGIN ───────────────────────────────
  Future<void> _login() async {
    setState(() => _isLoading = true);

    try {
      await AuthService.login(
        email: _emailCtrl.text.trim(),
        password: _passCtrl.text,
      );

      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/home');
    } catch (e) {
      _showSnack(e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  // ─── VOICE LOGIN ───────────────────────────────
  Future<void> _toggleVoiceLogin() async {
    if (_isRecording) {
      final path = await _recorder.stopRecording();

      setState(() {
        _isRecording = false;
        _voicePath = path?.path;
      });

      await _voiceLogin();
    } else {
      await _recorder.startRecording();

      setState(() {
        _isRecording = true;
        _voicePath = null;
      });
    }
  }

  Future<void> _voiceLogin() async {
    if (_voicePath == null || _voicePath!.isEmpty) return;

    setState(() => _isLoading = true);

    try {
      await AuthService.voiceLogin(File(_voicePath!));

      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/home');
    } catch (e) {
      _showSnack(e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showSnack(String msg, {bool error = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: error ? Colors.red : Colors.teal,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Login")),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            TextField(
              controller: _emailCtrl,
              decoration: const InputDecoration(labelText: "Email"),
            ),
            TextField(
              controller: _passCtrl,
              decoration: const InputDecoration(labelText: "Password"),
              obscureText: true,
            ),

            const SizedBox(height: 20),

            ElevatedButton(
              onPressed: _isLoading ? null : _login,
              child: const Text("Login"),
            ),

            // ✅ REGISTER BUTTON ADDED
            TextButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => const RegisterScreen(),
                  ),
                );
              },
              child: const Text("Don't have an account? Register"),
            ),

            const Divider(height: 40),

            ElevatedButton.icon(
              onPressed: _toggleVoiceLogin,
              icon: Icon(_isRecording ? Icons.stop : Icons.mic),
              label: Text(_isRecording ? "Stop Voice Login" : "Voice Login"),
            ),

            const SizedBox(height: 10),

            Text(
              _voicePath ?? "No voice recorded",
              style: const TextStyle(color: Colors.grey),
            ),

            if (_isLoading)
              const Padding(
                padding: EdgeInsets.only(top: 20),
                child: CircularProgressIndicator(),
              ),
          ],
        ),
      ),
    );
  }
}