/// VoiceAttend AI – Pulse Button Widget
/// =========================================
/// An animated microphone button that pulses when recording.
library;

import 'package:flutter/material.dart';

class PulseButton extends StatefulWidget {
  /// Whether the mic is currently recording (drives the pulse animation).
  final bool isRecording;

  /// Callback when the button is tapped.
  final VoidCallback onPressed;

  const PulseButton({
    super.key,
    required this.isRecording,
    required this.onPressed,
  });

  @override
  State<PulseButton> createState() => _PulseButtonState();
}

class _PulseButtonState extends State<PulseButton>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double>   _scaleAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _scaleAnim = Tween<double>(begin: 1.0, end: 1.18).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void didUpdateWidget(PulseButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isRecording) {
      _controller.repeat(reverse: true);
    } else {
      _controller.stop();
      _controller.reset();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final Color bgColor = widget.isRecording
        ? Colors.redAccent
        : const Color(0xFF00C9A7);

    return GestureDetector(
      onTap: widget.onPressed,
      child: AnimatedBuilder(
        animation: _scaleAnim,
        builder: (_, child) => Transform.scale(
          scale: widget.isRecording ? _scaleAnim.value : 1.0,
          child: child,
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            // Outer glow ring
            if (widget.isRecording)
              Container(
                width: 130, height: 130,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.redAccent.withOpacity(0.15),
                ),
              ),

            // Main circle button
            Container(
              width: 110, height: 110,
              decoration: BoxDecoration(
                shape:    BoxShape.circle,
                color:    bgColor,
                boxShadow: [
                  BoxShadow(
                    color:       bgColor.withOpacity(0.45),
                    blurRadius:  24,
                    spreadRadius: 4,
                  ),
                ],
              ),
              child: Icon(
                widget.isRecording ? Icons.stop : Icons.mic,
                color: Colors.white,
                size: 44,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
