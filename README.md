# ♟️ Intelligent Chess Game Review System

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.0%2B-green)
![Stockfish](https://img.shields.io/badge/Stockfish-16%2B-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

A powerful, full-stack chess analysis application that provides Grandmaster-level feedback on your games. Powered by the **Stockfish** engine and a custom-built **Move Classification System**, this tool parses your games move-by-move to identify brilliance, blunders, and everything in between.

## 🚀 Features

### 🧠 Advanced Move Analysis Engine
*   **Automated Classification**: The core `MoveAnalyzer` class (`analyzer.py`) evaluates every move against Stockfish's optimal lines using strict business rules.
    *   **Brilliant (!!)**: Detects sound material sacrifices that lead to a winning advantage (verified by deep search).
    *   **Great (!)**: The only good move in a difficult position, or a lesser sacrifice.
    *   **Best (★)**: The engine's top choice (or a forced move / tied best).
    *   **Book (📖)**: Recognizes standard opening theory moves (limited to the first 5 full moves).
    *   **Mistake (?) / Blunder (??)**: Calculated based on win probability loss (e.g., losing > 20% win chance).
*   **Accuracy Scoring**: Computes 0-100 accuracy scores based on win probability delta, position complexity, and material penalties.
*   **Coach Reasoning**: Generates natural language explanations for *why* a move was good or bad (e.g., "You missed a forced mate sequence" or "Sacrifice unsound").

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
    *   Includes robust error handling and custom User-Agent headers.

### 🎨 Modern "Glassmorphism" UI
*   **Interactive Board**: Built with `chessboard.js` and `chess.js` for seamless playback.
*   **Visual Annotations**:
    *   Glyphs (!!, ?, ?!) overlay on the board.
    *   **Best Move Arrows**: Automatically drawn with SVG when a player blunders, showing the missed opportunity.
*   **Data Visualization**:
    *   **Advantage Chart**: Real-time Chart.js line graph showing the evaluation swing.
    *   **Evaluation Bar**: Dynamic HTML/CSS bar tracking the winning probability (absolute White perspective).
*   **Responsive Design**: A dark-themed, glass-styled interface using CSS variables and backdrop filters.

---

## 🛠️ Technical Architecture

### 1. Analysis Logic (`analyzer.py`)
The heart of the system is the `MoveAnalyzer` class. It employs a multi-step evaluation pipeline:
1.  **Pre-Move Analysis**: Uses provided engine evaluations of the position *before* the move.
2.  **Move Execution**: Simulates the player's move.
3.  **Post-Move Analysis**: Uses provided engine evaluations of the position *after* the move.
4.  **Metric Calculation**: Computes `win_delta` (win probability loss), `material_delta`, and `accuracy`.
5.  **Strict Business Rules**:
    *   **Sacrifice Verification**: If a material sacrifice is detected, the engine re-verifies at higher depth to ensure soundness.
    *   **Mate Detection**: Checks for forced mates, missed mates, and mate threats.
    *   **Normalization**: Ensures CP scores are relative to the correct side before classification.

### 2. Opening Detection (`openings.py`)
*   Uses **EPD (Extended Position Description)** hashing to identify openings.
*   Maps positions to a curated dictionary of **ECO (Encyclopedia of Chess Openings)** codes and names.
*   **NOTE**: The Opening Book logic in `server.py` limits book moves to the first **5 full moves** of the game.

### 3. Server Integration (`server.py`)
*   Manages the Stockfish process lifecycle (opens/closes engine context).
*   Runs **MultiPV** searches to provide context (alternative moves) for the analyzer.
*   Aggregates "Match Accuracy" and classifies the game outcome.

---

## 📦 Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/chess-review-system.git
    cd chess-review-system
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
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
├── book.py              # Legacy Opening Book manager
├── stockfish.exe        # Chess engine binary (not included in repo)
├── requirements.txt     # Python dependencies
├── .gitignore           # Git ignore rules
├── templates/
│   └── index.html       # Main frontend application (Single Page App)
└── static/
    ├── css/             # Stylesheets
    ├── img/             # Chesspieces graphics
    └── js/              # Client-side libraries (jquery, chessboard, chess.js)
```

## 🤝 Contributing
Contributions are welcome! Please open an issue or submit a pull request for any bugs or feature enhancements.

## 📄 License
This project is open-source and available under the [MIT License](LICENSE).
