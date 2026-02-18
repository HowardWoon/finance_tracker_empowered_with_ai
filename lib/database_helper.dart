import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart' show kIsWeb; // Detects if running on Web
import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';
import 'package:shared_preferences/shared_preferences.dart'; // Web Storage

class TransactionModel {
  final int? id;
  final String title;
  final double amount;
  final String type; 
  final String category; 
  final String date;

  TransactionModel({
    this.id, 
    required this.title, 
    required this.amount, 
    required this.type, 
    required this.category,
    required this.date
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id, 
      'title': title, 
      'amount': amount, 
      'type': type, 
      'category': category,
      'date': date
    };
  }

  factory TransactionModel.fromMap(Map<String, dynamic> map) {
    return TransactionModel(
      id: map['id'],
      title: map['title'],
      amount: map['amount'],
      type: map['type'],
      category: map['category'],
      date: map['date'],
    );
  }
}

class DatabaseHelper {
  static final DatabaseHelper instance = DatabaseHelper._init();
  static Database? _sqfliteDb;

  DatabaseHelper._init();

  // --- 1. GET DATA (Smart Switch) ---
  Future<List<TransactionModel>> getAllTransactions() async {
    if (kIsWeb) {
      // WEB MODE: Load from Browser Storage
      final prefs = await SharedPreferences.getInstance();
      final String? dataString = prefs.getString('transactions');
      if (dataString == null) return [];
      
      final List<dynamic> jsonList = jsonDecode(dataString);
      return jsonList.map((json) => TransactionModel.fromMap(json)).toList();
    } else {
      // MOBILE MODE: Load from SQL Database
      final db = await _getMobileDb();
      final result = await db.query('transactions', orderBy: 'date DESC');
      return result.map((json) => TransactionModel.fromMap(json)).toList();
    }
  }

  // --- 2. SAVE DATA (Smart Switch) ---
  Future<void> insertTransaction(TransactionModel transaction) async {
    if (kIsWeb) {
      // WEB MODE: Save to Browser Storage
      final prefs = await SharedPreferences.getInstance();
      final List<TransactionModel> currentList = await getAllTransactions();
      
      final newItem = TransactionModel(
        id: DateTime.now().millisecondsSinceEpoch, // Generate fake ID for web
        title: transaction.title,
        amount: transaction.amount,
        type: transaction.type,
        category: transaction.category,
        date: transaction.date
      );
      
      currentList.add(newItem);
      
      final String encoded = jsonEncode(currentList.map((e) => e.toMap()).toList());
      await prefs.setString('transactions', encoded);
      
    } else {
      // MOBILE MODE: Save to SQL Database
      final db = await _getMobileDb();
      await db.insert('transactions', transaction.toMap());
    }
  }

  // --- MOBILE DB SETUP (Hidden from Web) ---
  Future<Database> _getMobileDb() async {
    if (_sqfliteDb != null) return _sqfliteDb!;
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, 'smart_finance.db');
    _sqfliteDb = await openDatabase(path, version: 1, onCreate: (db, version) {
      return db.execute('''
        CREATE TABLE transactions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          amount REAL NOT NULL,
          type TEXT NOT NULL,
          category TEXT NOT NULL,
          date TEXT NOT NULL
        )
      ''');
    });
    return _sqfliteDb!;
  }
}