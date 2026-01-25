### **Step 1: Install Python Dependencies**

Navigate to the project directory in your terminal and run the following command to install all the necessary Python libraries listed in `requirements.txt`.

```bash
pip install -r requirements.txt
```
This will install `pandas`, `ib_insync`, `fastapi`, and other dependencies.

---

### **Step 2: Run the Application**

Make sure your Interactive Brokers TWS or Gateway is running, then start the trading bot:

```bash
python main.py
```

This command will:
1.  Start the main orchestrator process.
2.  Launch the **Analysis Service**, **Trade Service**, and **Invalidation Service** as separate, concurrent processes.
3.  You will see log messages from `[Main]`, `[AnalysisService]`, and `[TradeService]` in your console.

To stop the application, press `Ctrl+C` in the terminal where it is running.
