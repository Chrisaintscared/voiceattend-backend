// lib/screens/admin_screen.dart
// Admin dashboard: manage users, update roles, view all attendance logs.

import 'package:flutter/material.dart';
import '../services/auth_service.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  List<Map<String, dynamic>> _users      = [];
  List<Map<String, dynamic>> _attendance = [];
  bool _loadingUsers = true;
  bool _loadingLogs  = true;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _loadUsers();
    _loadLogs();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  // ─── Data loading ────────────────────────────────────────────────────
  Future<void> _loadUsers() async {
    setState(() => _loadingUsers = true);
    try {
      final users = await AuthService.adminListUsers();
      setState(() => _users = users);
    } catch (e) {
      _showSnack('Could not load users: $e', error: true);
    } finally {
      setState(() => _loadingUsers = false);
    }
  }

  Future<void> _loadLogs() async {
    setState(() => _loadingLogs = true);
    try {
      final logs = await AuthService.adminGetAttendance();
      setState(() => _attendance = logs);
    } catch (e) {
      _showSnack('Could not load logs: $e', error: true);
    } finally {
      setState(() => _loadingLogs = false);
    }
  }

  // ─── Actions ──────────────────────────────────────────────────────────
  Future<void> _deleteUser(String userId, String name) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete user'),
        content: Text('Remove "$name" and all their data?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await AuthService.adminDeleteUser(userId);
      setState(() => _users.removeWhere((u) => u['id'] == userId));
      _showSnack('User deleted');
    } catch (e) {
      _showSnack('Delete failed: $e', error: true);
    }
  }

  Future<void> _updateRole(String userId, String currentRole) async {
    final newRole = currentRole == 'admin' ? 'user' : 'admin';
    try {
      await AuthService.adminUpdateRole(userId, newRole);
      await _loadUsers();
      _showSnack('Role updated to $newRole');
    } catch (e) {
      _showSnack('Role update failed: $e', error: true);
    }
  }

  void _showSnack(String msg, {bool error = false}) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? Colors.red.shade700 : Colors.teal,
    ));
  }

  // ─── Build ────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Admin panel'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () async {
              await AuthService.logout();
              if (mounted) Navigator.pushReplacementNamed(context, '/login');
            },
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          tabs: [
            Tab(
              icon: const Icon(Icons.people_outline),
              text: 'Users (${_users.length})',
            ),
            Tab(
              icon: const Icon(Icons.list_alt),
              text: 'Attendance',
            ),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _buildUsersTab(),
          _buildAttendanceTab(),
        ],
      ),
    );
  }

  // ─── Users tab ────────────────────────────────────────────────────────
  Widget _buildUsersTab() {
    if (_loadingUsers) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_users.isEmpty) {
      return const Center(child: Text('No users found'));
    }
    return RefreshIndicator(
      onRefresh: _loadUsers,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _users.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (_, i) {
          final u = _users[i];
          final isAdmin = u['role'] == 'admin';
          return Card(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: isAdmin ? Colors.purple.shade100 : Colors.teal.shade100,
                child: Text(
                  (u['name'] as String? ?? '?')[0].toUpperCase(),
                  style: TextStyle(
                    color: isAdmin ? Colors.purple.shade800 : Colors.teal.shade800,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              title: Text(u['name'] ?? '—',
                  style: const TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(u['email'] ?? ''),
                  const SizedBox(height: 2),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: isAdmin
                          ? Colors.purple.shade100
                          : Colors.teal.shade100,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      u['role'] ?? 'user',
                      style: TextStyle(
                        fontSize: 11,
                        color: isAdmin
                            ? Colors.purple.shade800
                            : Colors.teal.shade800,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
              isThreeLine: true,
              trailing: PopupMenuButton<String>(
                onSelected: (action) {
                  if (action == 'delete') {
                    _deleteUser(u['id'], u['name'] ?? 'this user');
                  } else if (action == 'role') {
                    _updateRole(u['id'], u['role']);
                  }
                },
                itemBuilder: (_) => [
                  PopupMenuItem(
                    value: 'role',
                    child: Text(isAdmin
                        ? 'Demote to user'
                        : 'Promote to admin'),
                  ),
                  const PopupMenuItem(
                    value: 'delete',
                    child: Text(
                      'Delete user',
                      style: TextStyle(color: Colors.red),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  // ─── Attendance tab ───────────────────────────────────────────────────
  Widget _buildAttendanceTab() {
    if (_loadingLogs) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_attendance.isEmpty) {
      return const Center(child: Text('No attendance records'));
    }
    return RefreshIndicator(
      onRefresh: _loadLogs,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _attendance.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (_, i) {
          final log = _attendance[i];
          final confidence = (log['confidence'] as num?)?.toDouble() ?? 0.0;
          return ListTile(
            leading: const CircleAvatar(
              backgroundColor: Color(0xFFE1F5EE),
              child: Icon(Icons.check, color: Color(0xFF0F6E56), size: 18),
            ),
            title: Text(log['name'] ?? 'Unknown',
                style: const TextStyle(fontWeight: FontWeight.w500)),
            subtitle: Text(
              '${log['email'] ?? '—'}\n${log['timestamp'] ?? ''}',
            ),
            isThreeLine: true,
            trailing: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  log['status'] ?? 'present',
                  style: const TextStyle(
                      fontWeight: FontWeight.w500, color: Colors.teal),
                ),
                Text(
                  '${(confidence * 100).toStringAsFixed(0)}%',
                  style: TextStyle(
                    fontSize: 12,
                    color: confidence > 0.85
                        ? Colors.green.shade700
                        : Colors.orange.shade700,
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
