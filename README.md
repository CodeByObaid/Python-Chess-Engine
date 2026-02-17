# ♟️ Intelligent Chess Game Review System

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.0%2B-green)
![Stockfish](https://img.shields.io/badge/Stockfish-16%2B-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

A powerful, full-stack chess analysis application that provides Grandmaster-level feedback on your games. Powered by the **Stockfish** engine and a custom-built **Move Classification System**, this tool parses your games move-by-move to identify brilliance, blunders, and everything in between.

## 🚀 Features

### 🧠 Advanced Move Analysis Engine
*   **Automated Classification**: The core `MoveAnalyzer` class evaluates every move against Stockfish's optimal lines.
    *   **Brilliant (!!)**: Detects material sacrifices that lead to a winning advantage (depth-verified).
    *   **Great (!)**: Critical moves in complex positions that maintain an advantage.
    *   **Best (★)**: The engine's top choice (or equivalent evaluation).
    *   **Book (📖)**: Recognizes standard opening theory moves using an EPD-based opening database.
    *   **Mistake (?) / Blunder (??)**: Calculated based on "Normalized Evaluation Loss" (Centipawn loss adjusted for the game phase and winning chances).
*   **Phase Detection**: Dynamically identifies **Opening**, **Middlegame**, and **Endgame** phases to adjust analysis sensitivity.
*   **Coach Reasoning**: Generates natural language explanations for *why* a move was good or bad (e.g., "You missed a forced mate sequence" or "You hung a piece").

### 🔌 Robust Backend API (Flask)
*   **`/analyze_full_game` Endpoint**:
    *   Accepts raw PGN text.
    *   Parses games using `python-chess`.
    *   Manages the UCI (Universal Chess Interface) connection to Stockfish.
    *   Returns a detailed JSON object with per-move stats, accuracy scores (0-100%), and listing of key threats.
*   **`/fetch_games` Endpoint**:
    *   Integrates directly with the **Chess.com Public API**.
    *   Fetches game archives for any valid username.
    *   Parses JSON responses to extract PGNs, results, and opponent details.
    *   Includes robust error handling and custom User-Agent headers to ensure reliable fetching.

### 🎨 Modern "Glassmorphism" UI
*   **Interactive Board**: Built with `chessboard.js` and `chess.js` for seamless playback.
*   **Visual Annotations**:
    *   Glyphs (!!, ?, ?!) overlay on the board.
    *   **Best Move Arrows**: Automatically drawn with SVG when a player blunders, showing the missed opportunity.
*   **Data Visualization**:
    *   **Advantage Chart**: Real-time Chart.js line graph showing the evaluation swing.
    *   **Evaluation Bar**: Dynamic HTML/CSS bar tracking the winning probability.
*   **Responsive Design**: A dark-themed, glass-styled interface using CSS variables and backdrop filters.

---

## 🛠️ Technical Architecture

### 1. Analysis Logic (`analyzer.py`)
The heart of the system is the `MoveAnalyzer` class. It employs a multi-step evaluation pipeline:
1.  **Pre-Move Analysis**: Runs Stockfish (MultiPV=5) on the position *before* the move to establish the baseline "Best" evaluation.
2.  **Move Execution**: Pushes the player's move to the board.
3.  **Post-Move Analysis**: Runs Stockfish again to determine the new evaluation.
4.  **Delta Calculation**: Computes `eval_loss` (raw centipawn difference).
5.  **Normalization**: Applies `normalize_loss()` to weigh mistakes differently in winning vs. losing positions (e.g., a +1.0 loss is huge in an equal game, but negligible if you are already +10.0).
6.  **Classification Tree**: Passes all metrics (rank, loss, material delta, mate threats) into `classify_move()` to determine the move label.

### 2. Opening Detection (`openings.py`)
*   Uses **EPD (Extended Position Description)** hashing to identify openings.
*   Hashes the board position (excluding clock/move counters) to find transpositions.
*   Maps positions to a curated dictionary of **ECO (Encyclopedia of Chess Openings)** codes and names.

### 3. Server Integration (`server.py`)
*   Manages the Stockfish process lifecycle (opens/closes engine context).
*   Aggregates "Match Accuracy" by averaging the quality of all moves using an exponential decay formula based on normalized loss.

---

## 📦 Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/chess-review-system.git
    cd chess-review-system
    ```

2.  **Install Dependencies**:
    ```bash
    pip install flask python-chess requests
    ```

3.  **Setup Stockfish**:
    *   Download the Stockfish engine for your OS from [stockfishchess.org](https://stockfishchess.org/download/).
    *   Place the `stockfish.exe` (or binary) in the project root directory.
    *   *Optional*: Update `ENGINE_PATH` in `server.py` if placed elsewhere.

4.  **Run the Application**:
    ```bash
    python server.py
    ```

5.  **Access the UI**:
    *   Open your browser and navigate to `http://localhost:5000`.

## 🕹️ Usage

1.  **Load a Game**:
    *   **Paste PGN**: Copy PGN text from Lichess/Chess.com and paste it into the text area.
    *   **Fetch from Chess.com**: Enter a username in the sidebar and click the Search icon to load recent games.
2.  **Analyze**: Click "Analyze Game". The system will process the moves (this may take a few seconds depending on game length).
3.  **Review**:
    *   Use the arrow keys or on-screen controls to step through the game.
    *   Click any move in the **Move List** to jump to that position.
    *   Read the **Coach's Feedback** in the sidebar for explanations of your mistakes.

## 📂 Project Structure

```
├── analyzer.py          # Core logic for move classification and reasoning
├── server.py            # Flask server and API endpoints
├── openings.py          # ECO opening codes and detection logic
├── stockfish.exe        # Chess engine binary (not included in repo)
├── templates/
│   └── index.html       # Main frontend application (Single Page App)
└── static/
    ├── css/             # Chessboard.js styles
    ├── img/             # Chesspieces graphics
    └── js/              # Client-side libraries (jquery, chessboard, chess.js)
```

## 🤝 Contributing
Contributions are welcome! Please open an issue or submit a pull request for any bugs or feature enhancements.

## 📄 License
This project is open-source and available under the [MIT License](LICENSE).
