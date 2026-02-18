import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart'; 
import 'package:url_launcher/url_launcher.dart'; 
import 'package:intl/intl.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http; // For AI Connection
import 'package:flutter_markdown/flutter_markdown.dart'; // For nice AI text
import 'database_helper.dart';

// --- !!! PASTE YOUR API KEY HERE !!! ---
const String apiKey = "AIzaSyDplGXumkldSduvWRLjmtkeGusDfF9RX1I"; 
// ---------------------------------------

void main() {
  runApp(const MaterialApp(
    debugShowCheckedModeBanner: false,
    title: "Smart Budget AI",
    home: SmartFinanceHome(),
  ));
}

class SmartFinanceHome extends StatefulWidget {
  const SmartFinanceHome({super.key});

  @override
  State<SmartFinanceHome> createState() => _SmartFinanceHomeState();
}

class _SmartFinanceHomeState extends State<SmartFinanceHome> {
  // Controllers
  final titleController = TextEditingController();
  final amountController = TextEditingController();
  final chatController = TextEditingController(); // For the AI Chat
  
  String _selectedCategory = 'Food';
  final List<String> _categories = ['Food', 'Transport', 'Shopping', 'Bills', 'Entertainment', 'Salary', 'Other'];

  // Data
  List<TransactionModel> _transactions = [];
  double _totalIncome = 0;
  double _totalExpense = 0;
  
  // AI State
  String _aiResponse = "Ask me anything about your finances! e.g., 'Can I afford a Genting trip?'";
  bool _isAiLoading = false;

  @override
  void initState() {
    super.initState();
    _refreshData();
  }

  void _refreshData() async {
    final data = await DatabaseHelper.instance.getAllTransactions();
    double income = 0;
    double expense = 0;
    
    for (var t in data) {
      if (t.type == 'income') income += t.amount;
      else expense += t.amount;
    }

    setState(() {
      _transactions = data;
      _totalIncome = income;
      _totalExpense = expense;
    });
  }

  // --- THE REAL AI BRAIN ---
  Future<void> _askGeminiAI() async {
    final userQuestion = chatController.text;
    if (userQuestion.isEmpty) return;

    setState(() {
      _isAiLoading = true;
      _aiResponse = "Thinking..."; 
    });

    // 1. Prepare the Data Context for the AI
    String financialContext = """
    My Financial Data:
    - Total Income: RM ${_totalIncome.toStringAsFixed(2)}
    - Total Expenses: RM ${_totalExpense.toStringAsFixed(2)}
    - Balance: RM ${(_totalIncome - _totalExpense).toStringAsFixed(2)}
    
    Recent Transactions:
    ${_transactions.take(10).map((e) => "- ${e.title}: RM${e.amount} (${e.category})").join('\n')}
    """;

    // 2. Send to Google Gemini API
    final url = Uri.parse('https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=$apiKey');
    
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          "contents": [{
            "parts": [{
              "text": "You are a helpful financial advisor. Analyze this data: $financialContext. \n\n User Question: $userQuestion. \n\n Answer concisely and analyze the risk."
            }]
          }]
        }),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final String botReply = data['candidates'][0]['content']['parts'][0]['text'];
        setState(() {
          _aiResponse = botReply;
        });
      } else {
        setState(() {
          _aiResponse = "Error: Please check your API Key. (Status: ${response.statusCode})";
        });
      }
    } catch (e) {
      setState(() {
        _aiResponse = "Failed to connect to AI. Check your internet.";
      });
    } finally {
      setState(() {
        _isAiLoading = false;
        chatController.clear();
      });
    }
  }

  Future<void> _openTouchNGo() async {
    final Uri url = Uri.parse("https://www.touchngo.com.my/"); 
    if (!await launchUrl(url, mode: LaunchMode.externalApplication)) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Could not open app")));
    }
  }

  void _addTransaction(String type) async {
    final title = titleController.text;
    final amount = double.tryParse(amountController.text) ?? 0.0;

    if (title.isEmpty || amount <= 0) return;

    final tx = TransactionModel(
      title: title,
      amount: amount,
      type: type,
      category: type == 'income' ? 'Salary' : _selectedCategory,
      date: DateFormat('yyyy-MM-dd').format(DateTime.now()),
    );

    await DatabaseHelper.instance.insertTransaction(tx);
    titleController.clear();
    amountController.clear();
    Navigator.pop(context);
    _refreshData();
  }

  void _showAddModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => Padding(
        padding: EdgeInsets.only(
          top: 20, left: 20, right: 20,
          bottom: MediaQuery.of(context).viewInsets.bottom + 20
        ),
        child: StatefulBuilder(
          builder: (context, setModalState) { 
            return Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text("New Transaction", style: GoogleFonts.poppins(fontSize: 18, fontWeight: FontWeight.bold)),
                const SizedBox(height: 10),
                TextField(controller: titleController, decoration: const InputDecoration(labelText: 'Description', border: OutlineInputBorder())),
                const SizedBox(height: 10),
                TextField(controller: amountController, decoration: const InputDecoration(labelText: 'Amount (RM)', border: OutlineInputBorder()), keyboardType: TextInputType.number),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  value: _selectedCategory,
                  items: _categories.map((String category) {
                    return DropdownMenuItem(value: category, child: Text(category));
                  }).toList(),
                  onChanged: (newValue) => setModalState(() => _selectedCategory = newValue!),
                  decoration: const InputDecoration(labelText: 'Category', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 20),
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () => _addTransaction('income'),
                        style: ElevatedButton.styleFrom(backgroundColor: Colors.green, padding: const EdgeInsets.symmetric(vertical: 15)),
                        child: const Text('Income', style: TextStyle(color: Colors.white)),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () => _addTransaction('expense'),
                        style: ElevatedButton.styleFrom(backgroundColor: Colors.red, padding: const EdgeInsets.symmetric(vertical: 15)),
                        child: const Text('Expense', style: TextStyle(color: Colors.white)),
                      ),
                    ),
                  ],
                )
              ],
            );
          }
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    double total = _totalIncome + _totalExpense;
    String percentageText = "0%";
    if (total > 0 && _totalExpense > 0) {
      percentageText = "${((_totalExpense / total) * 100).toStringAsFixed(0)}%";
    }

    return Scaffold(
      backgroundColor: Colors.grey[100],
      appBar: AppBar(
        title: Text('Smart Budget AI', style: GoogleFonts.poppins(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.blueAccent,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.account_balance_wallet),
            tooltip: 'Touch n Go',
            onPressed: _openTouchNGo,
          )
        ],
      ),
      body: SingleChildScrollView(
        child: Column(
          children: [
            // --- AI CHAT CARD (NEW!) ---
            Container(
              margin: const EdgeInsets.all(16),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.blueAccent.withOpacity(0.3)),
                boxShadow: [BoxShadow(color: Colors.blue.withOpacity(0.1), blurRadius: 10, offset: const Offset(0, 5))]
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.psychology, color: Colors.blueAccent),
                      const SizedBox(width: 8),
                      Text("Ask the AI Advisor", style: GoogleFonts.poppins(fontWeight: FontWeight.bold, fontSize: 16)),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Container(
                    height: 100, // Fixed height for response area
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(color: Colors.grey[50], borderRadius: BorderRadius.circular(8)),
                    child: SingleChildScrollView(
                      child: _isAiLoading 
                        ? const Center(child: CircularProgressIndicator()) 
                        : MarkdownBody(data: _aiResponse), // Renders pretty text
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: chatController,
                          decoration: const InputDecoration(
                            hintText: "e.g. Can I take RM200 from daddy?",
                            border: OutlineInputBorder(),
                            contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton(
                        onPressed: _askGeminiAI,
                        icon: const Icon(Icons.send, color: Colors.blueAccent),
                        style: IconButton.styleFrom(backgroundColor: Colors.blue.shade50),
                      )
                    ],
                  )
                ],
              ),
            ),
            
            // --- Stats Row ---
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0),
              child: Row(
                children: [
                  Expanded(child: _buildCard("Income", _totalIncome, Colors.green)),
                  const SizedBox(width: 10),
                  Expanded(child: _buildCard("Expenses", _totalExpense, Colors.red)),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // --- Chart ---
            Container(
              height: 200,
              padding: const EdgeInsets.all(10),
              child: (_totalIncome == 0 && _totalExpense == 0) 
              ? const Center(child: Text("Add expenses to see the chart")) 
              : PieChart(
                  PieChartData(
                    sections: [
                      PieChartSectionData(value: _totalIncome == 0 ? 0.1 : _totalIncome, color: Colors.greenAccent, radius: 40, showTitle: false),
                      PieChartSectionData(
                        value: _totalExpense == 0 ? 0 : _totalExpense, 
                        color: Colors.redAccent, 
                        radius: 50, 
                        title: percentageText, 
                        titleStyle: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)
                      ),
                    ],
                    centerSpaceRadius: 40,
                  ),
                ),
            ),

            // --- Transaction List ---
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Text("Recent Transactions", style: GoogleFonts.poppins(fontWeight: FontWeight.bold, fontSize: 18)),
            ),
            ListView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _transactions.length,
              itemBuilder: (context, index) {
                final tx = _transactions[index];
                return Card(
                  margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 5),
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: tx.type == 'income' ? Colors.green.shade50 : Colors.red.shade50,
                      child: Icon(
                        _getCategoryIcon(tx.category), 
                        color: tx.type == 'income' ? Colors.green : Colors.red,
                        size: 20,
                      ),
                    ),
                    title: Text(tx.title, style: const TextStyle(fontWeight: FontWeight.bold)),
                    subtitle: Text("${tx.category} • ${tx.date}"),
                    trailing: Text(
                      "${tx.type == 'income' ? '+' : '-'} RM${tx.amount.toStringAsFixed(2)}",
                      style: TextStyle(fontWeight: FontWeight.bold, color: tx.type == 'income' ? Colors.green : Colors.red),
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddModal(context),
        backgroundColor: Colors.blueAccent,
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }

  IconData _getCategoryIcon(String cat) {
    switch (cat) {
      case 'Food': return Icons.fastfood;
      case 'Transport': return Icons.directions_car;
      case 'Shopping': return Icons.shopping_bag;
      case 'Bills': return Icons.receipt_long;
      case 'Entertainment': return Icons.movie;
      case 'Salary': return Icons.attach_money;
      default: return Icons.category;
    }
  }

  Widget _buildCard(String title, double value, Color color) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [BoxShadow(color: Colors.grey.withOpacity(0.1), blurRadius: 5, offset: const Offset(0, 2))]
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: TextStyle(color: Colors.grey[600], fontSize: 12)),
          const SizedBox(height: 5),
          Text("RM${value.toStringAsFixed(2)}", style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 18)),
        ],
      ),
    );
  }
}