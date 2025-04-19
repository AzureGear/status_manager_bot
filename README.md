
## Telegram Bot for Activity Monitoring Automation (Status Manager)  

Automated tracking and management of groups activities (students, employees, etc.) with real-time status updates. Built with `python-telegram-bot`.

## Quick Start Guide  
1. **Configure Environment**  
   Add your bot token to `.env`:  
   ```ini
   API_BOT_TOKEN="your_bot_token_here"
   ```

2. **Initialize Sample Data**  
   Generate demo user accounts:  
   ```bash
   python utils.py
   ```

3. **Launch Application**  
   Start the bot service:  
   ```bash
   python az_bot.py
   ```

## Description 

**Use Case Example:**  
- Managers (teacher, leader) can:  
  ✓ Set attendance records  
  ✓ Track assignment completion  
  ✓ View aggregated group statistics  
- Works for both individual users and group supervisors  
- Export data

**Key Differentiator:**  
Database-free architecture using:  
- Smart JSON storage system  
- Auto-generated relational mappings  
- Lightweight file-based operations  

**Architecture Highlights:**  
No-SQL approach minimizes deployment complexity  
Self-maintaining data relationships  
GDPR-compliant data handling  
Preconfigured authorization queries for role-based access control

<img src="assets/demo.gif" alt="Демо" width="450" align="center">
