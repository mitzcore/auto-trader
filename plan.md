# Project Plan: Automated Trading Signal Bot

## Goal
The primary goal is to create an automated trading signal generator that systematically and unemotionally identifies high-probability candlestick patterns and structural market zones (such as demand zones) across multiple timeframes.

## Objectives
1.  **Data Ingestion:** Reliably connect to the Interactive Brokers API via IB Gateway and stream real-time market data for a target symbol (SPY).
2.  **Data Processing:** Efficiently process the raw data stream into multiple, distinct candlestick bar timeframes (2m, 3m, 5m, 10m, 15m, 30m, 1h, 2h, 4h, 1D).
3.  **Pattern Recognition:** Implement a decoupled and testable engine to identify specific single-candle and multi-candle patterns.
4.  **Zone Detection:** Implement logic to identify structural demand zones based on specific multi-candle formations.
5.  **Signal Alerting:** Generate a clear, real-time alert (logged to a file) that specifies the pattern, the timeframe, and the timestamp of its appearance.
6.  **System Design:** Ensure the final application is reliable, performant, and architecturally simple for continuous, unattended operation.

***

### ## Development Phases & Features

This plan rolls out features in logical phases, ensuring a solid foundation before adding complexity.

#### **Phase 1: The Core Engine (MVP)**
* **Goal:** To build a functional data pipeline that can successfully connect to the market, process raw data, and generate all required multi-timeframe candlestick bars.
(Completed)

---

#### **Phase 2: Pattern Logic & Alerting**
* **Goal:** To implement the core business logic for identifying and alerting on the specified candlestick patterns.
(Completed)

---

#### **Phase 3: Refinement & Reliability**
* **Goal:** To add foundational features that make the application robust, maintainable, and ready for continuous operation.
(Completed)

---

#### **Phase 4: Demand Zone Detection**
* **Goal:** To implement an engine that identifies and logs structural demand zones based on a specific two-candle pattern.

| Step | Feature Description | Key Design Principle | Completion Criteria | Status |
| :--- | :--- | :--- | :--- | :--- |
| **4.1**| **Code Refactoring**| Move all single-candle pattern functions (`is_doji`, etc.) into a dedicated `algotrade/patterns.py` file to improve code organization and scalability. | The `main.py` file is cleaned of pattern logic, which is now imported from the new module. | 🔲 In Progress |
| **4.2**| **Demand Zone Logic**| Create a new `algotrade/analysis.py` module. Implement a function `detect_demand_zone` that identifies a two-candle sequence: a small-bodied bearish "setup" candle followed by a strong bullish "confirmation" candle (Marubozu or Near-Marubozu). | The function correctly identifies the pattern and returns a dictionary representing the zone (`top`, `bottom`, `timestamp`). | 🔲 In Progress |
| **4.3**| **Integration & Storage**| Modify the main historical scan loop to call the `detect_demand_zone` function. Store any detected zones in an in-memory list for the program's duration. | The main loop correctly uses the new analysis function. | 🔲 In Progress |
| **4.4**| **Logging**| Add structured logging to record the details of each detected demand zone, including its timeframe, timestamp, and price levels. | Newly identified demand zones are clearly printed to the log file. | 🔲 In Progress |

***

### ## Architectural Benefits

This design was chosen specifically to align with the core principle of **Simplicity**, which is critical for efficient development.

* **Declarative, Step-by-Step Logic:** The main loop is a simple, repeatable set of instructions, making it easy to develop and debug.
* **Stateless Processing:** The bar generation is stateless (it re-calculates everything from a master list each time). This avoids the tricky logic of managing multiple incomplete, streaming bars.
* **Reduced Complexity:** It eliminates the need for advanced concepts like multi-threading or complex, event-driven classes. The entire program flows from top to bottom in a single thread, making it trivial to reason about.