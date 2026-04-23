// lib/screens/register_screen.dart
import 'dart:io';
import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../services/audio_recorder_service.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();

  final _recorder = AudioRecorderService();

  bool _obscurePassword = true;
  bool _isRecording = false;
  bool _isLoading = false;

  String _role = "student"; // ✅ role added
  String? _voicePath;

  // ─── Voice Recording ───────────────────────────────
  Future<void> _toggleRecording() async {
    if (_isRecording) {
      final path = await _recorder.stopRecording();

      setState(() {
        _isRecording = false;
        _voicePath = path?.path;
      });
    } else {
      await _recorder.startRecording();

      setState(() {
        _isRecording = true;
        _voicePath = null;
      });
    }
  }

  // ─── Submit ───────────────────────────────
  Future<void> _submit() async {
    if (_voicePath == null || _voicePath!.isEmpty) {
      _showSnack("Please record your voice first", error: true);
      return;
    }

    setState(() => _isLoading = true);

    try {
      await AuthService.register(
        name: _nameCtrl.text.trim(),
        email: _emailCtrl.text.trim(),
        password: _passCtrl.text,
        role: _role, // ✅ send role
        voiceFile: File(_voicePath!),
      );

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
      appBar: AppBar(title: const Text("Register")),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            TextField(
              controller: _nameCtrl,
              decoration: const InputDecoration(labelText: "Name"),
            ),
            TextField(
              controller: _emailCtrl,
              decoration: const InputDecoration(labelText: "Email"),
            ),
            TextField(
              controller: _passCtrl,
              obscureText: _obscurePassword,
              decoration: InputDecoration(
                labelText: "Password",
                suffixIcon: IconButton(
                  icon: Icon(
                    _obscurePassword ? Icons.visibility_off : Icons.visibility,
                  ),
                  onPressed: () {
                    setState(() => _obscurePassword = !_obscurePassword);
                  },
                ),
              ),
            ),

            const SizedBox(height: 10),

            // ✅ ROLE DROPDOWN
            DropdownButton<String>(
              value: _role,
              isExpanded: true,
              items: const [
                DropdownMenuItem(value: "student", child: Text("Student")),
                DropdownMenuItem(value: "teacher", child: Text("Teacher")),
              ],
              onChanged: (value) {
                setState(() => _role = value!);
              },
            ),

            const SizedBox(height: 20),

            ElevatedButton.icon(
              onPressed: _toggleRecording,
              icon: Icon(_isRecording ? Icons.stop : Icons.mic),
              label: Text(_isRecording ? "Stop Recording" : "Record Voice"),
            ),

            const SizedBox(height: 10),

            Text(
              _voicePath ?? "No voice recorded",
              style: const TextStyle(color: Colors.grey),
            ),

            const SizedBox(height: 20),

            ElevatedButton(
              onPressed: _isLoading ? null : _submit,
              child: _isLoading
                  ? const CircularProgressIndicator()
                  : const Text("Register"),
            ),
          ],
        ),
      ),
    );
  }
}
