### **Step 1: Set Up Redis**

The services communicate through a Redis server. You need to have one running on your machine. Here are two common ways to do this on macOS.

**Option A: Using Docker (Recommended for ease of use)**

If you have Docker installed, you can start a Redis server with a single command. It will run in the background.

```bash
docker run --name algotrade-redis -p 6379:6379 -d redis
```

*   To stop the Redis container later: `docker stop algotrade-redis`
*   To start it again: `docker start algotrade-redis`

**Option B: Using Homebrew**

If you use Homebrew, you can install and run Redis directly on your system.

1.  **Install Redis:**
    ```bash
    brew install redis
    ```
2.  **Start Redis as a background service:**
    ```bash
    brew services start redis
    ```

As long as Redis is running on the default address (`127.0.0.1` at port `6379`), the application will connect to it automatically.

---

### **Step 2: Install Python Dependencies**

Navigate to the project directory in your terminal and run the following command to install all the necessary Python libraries listed in `requirements.txt`.

```bash
pip install -r requirements.txt
```
This will install `pandas`, `ib_insync`, and the `redis` client library.

---

### **Step 3: Run the Application**

Once Redis is running and the dependencies are installed, you can start the trading bot with a single command. Make sure your Interactive Brokers TWS or Gateway is also running.

```bash
python main.py
```

This command will:
1.  Start the main orchestrator process.
2.  Launch the **Analysis Service** and the **Trade Service** as two separate, concurrent processes.
3.  You will see log messages from `[Main]`, `[AnalysisService]`, and `[TradeService]` in your console, indicating that both are running and connected to IB and Redis.

To stop the application, press `Ctrl+C` in the terminal where it is running.
