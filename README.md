# Python-Chess-Engine
Chess Game Review System - Documentation
Detailed Code Explanation
1. Backend (
server.py
)
The backend is a Flask application that acts as the bridge between the user interface and the chess engine (Stockfish).

Game Analysis Endpoint (/analyze_full_game):
Accepts a PGN (Portable Game Notation) string.
Parses the game using python-chess.
Iterates through every move in the game.
Uses 
analyzer.py
 to evaluate each move against Stockfish's best moves.
Collects statistics (accuracy, inaccuracies, blunders, etc.) and detects the opening used.
Returns a JSON object containing move-by-move analysis, player stats, and opening info.
Game Fetching Endpoint (/fetch_games):
Connects to the Chess.com public API.
Retrieves the game archives for a specific username.
Fetches the most recent games from the latest archive.
Returns a list of games with results and valid PGNs for analysis.
2. Analysis Logic (
analyzer.py
)
This module contains the core intelligence of the review system, encapsulated in the 
MoveAnalyzer
 class.

Move Classification:
It compares the player's move with the engine's top choices.
Calculates eval_loss (difference in centipawn score) and normalized_loss (adjusted for winning/losing positions).
Classifies moves into categories: Brilliant, Great, Best, Book, Good, Inaccuracy, Mistake, Blunder, Miss.
"Brilliant" Detection: Checks for material sacrifices that lead to a winning position.
"Book" Detection: Identifies standard opening moves based on move number and low evaluation loss.
Coach Reasoning:
Generates human-readable explanations for every move (e.g., "You hung a piece!", "You found the only move that saves the position!").
Uses factors like material change, mate threats, and check status to generate context-aware feedback.
Phase Detection: Determines if the game is in the Opening, Middlegame, or Endgame to adjust analysis sensitivity.
3. Frontend (
templates/index.html
)
The user interface is built with HTML, CSS (Glassmorphism design), and JavaScript.

Interactive Board: Uses chessboard.js and chess.js for board rendering and game state management. Notifies the user of move quality using visual glyphs (!!, ??, ?!, etc.) directly on the board.
Visual Feedback:
Evaluation Bar: A dynamic bar on the left showing the current advantage (White vs. Black).
Arrow Drawing: Automatically draws arrows on the board to show the best move when the player makes a mistake or blunder.
Coach Feedback Box: Displays the text explanation for the current move.
Data Visualization:
Advantage Chart: A line chart (Chart.js) showing the swing of advantage throughout the game.
Move Table: A clickable list of moves with color-coded classifications.
Game Management:
Users can paste PGN directly or fetch recent games from Chess.com by username.
4. Opening Detection (
openings.py
)
Contains a dictionary mapping FEN (Forsyth–Edwards Notation) strings to ECO codes and opening names (e.g., "Sicilian Defence: Najdorf Variation").
Used to label the game with the specific opening played.
