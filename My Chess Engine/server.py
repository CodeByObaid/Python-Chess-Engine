import chess
import chess.engine
import chess.pgn
import math
import io
import requests
from flask import Flask, jsonify, request, render_template
from openings import detect_opening
from analyzer import MoveAnalyzer

app = Flask(__name__)

# CONFIGURATION
# Update this path if needed
ENGINE_PATH = r"C:\Users\MrLaptop\Desktop\python\My Chess Engine\stockfish.exe"

# Initialize Analyzer
analyzer = MoveAnalyzer(ENGINE_PATH)

# ==========================================
# 🌐 ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch_games', methods=['POST'])
def fetch_games():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        if not username: return jsonify({'status': 'error', 'message': 'Username required'})

        headers = {'User-Agent': 'ChessAnalysisApp/1.0 (contact@example.com)'}
        
        # 1. Get Archives
        archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
        print(f"Fetching from: {archives_url}")
        resp = requests.get(archives_url, headers=headers)
        
        if resp.status_code != 200: 
            print(f"Error: Status {resp.status_code} for user {username}")
            return jsonify({'status': 'error', 'message': f'User {username} not found (Status: {resp.status_code})'})
        
        archives = resp.json().get('archives', [])
        if not archives:
            return jsonify({'status': 'error', 'message': 'No game archives found'})

        # 2. Get Games from Latest Archive
        latest_url = archives[-1]
        games_resp = requests.get(latest_url, headers=headers)
        games_data = games_resp.json().get('games', [])
        
        # Filter and Sort (Latest first)
        games_list = []
        for g in sorted(games_data, key=lambda x: x.get('end_time', 0), reverse=True)[:10]:
            white = g.get('white', {})
            black = g.get('black', {})
            result = "Draw"
            if white.get('result') == 'win': result = "White Won"
            elif black.get('result') == 'win': result = "Black Won"
            
            games_list.append({
                'white': white.get('username'),
                'black': black.get('username'),
                'result': result,
                'pgn': g.get('pgn'),
                'url': g.get('url'),
                'date': g.get('end_time') # Timestamp
            })

        return jsonify({'status': 'success', 'games': games_list})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/analyze_full_game', methods=['POST'])
def analyze_full_game():
    try:
        data = request.get_json()
        pgn_text = data.get('pgn')
        if not pgn_text: return jsonify({'status': 'error', 'message': 'No PGN provided'})

        pgn_io = io.StringIO(pgn_text)
        game = chess.pgn.read_game(pgn_io)
        if game is None: return jsonify({'status': 'error', 'message': 'Invalid PGN'})

        board = game.board()
        
        # Player Names
        white_player = game.headers.get("White", "White")
        black_player = game.headers.get("Black", "Black")
        
        analysis_results = []
        stats = {k: {'brilliant':0, 'great':0, 'critical':0, 'best':0, 'good':0, 'book':0, 'inaccuracy':0, 'mistake':0, 'miss':0, 'blunder':0} for k in ['w', 'b']}
        acc_totals = {'w': 0, 'b': 0}
        move_counts = {'w': 0, 'b': 0}

        detected_opening = None

        # Use the engine context from python-chess directly if needed, 
        # but analyzer.analyze_move manages engine instances or can accept one.
        # For performance, we should spawn one engine and reuse it.
        
        with chess.engine.SimpleEngine.popen_uci(ENGINE_PATH) as engine:
            book_active = True # Track book chain inside the analysis loop
            
            for move in game.mainline_moves():
                turn = 'w' if board.turn == chess.WHITE else 'b'
                move_uci = move.uci()
                move_san = board.san(move) # Capture SAN before move

                # Analyze Move
                # Note: analyzer.analyze_move pushes the move to analyze 'after' metrics, then pops it.
                # However, it expects the board to be at the state BEFORE the move.
                # So we call it, get the result, then push the move on our local board loop.
                
                result = analyzer.analyze_move(board, move_uci, engine=engine)
                
                if "error" in result:
                    print(f"Error analyzing move {move_uci}: {result['error']}")
                    board.push(move)
                    continue

                classification = result['classification']
                
                # Book Logic Override
                label = classification.title()
                if book_active:
                    is_book_move = False
                    
                    # Rule 1: 1st White Move -> Always Book
                    if board.fullmove_number == 1 and turn == 'w':
                        is_book_move = True
                    
                    # Rule 2: Subsequent moves -> Book if "Best" (or Brilliant/Great)
                    elif classification in ['best', 'brilliant', 'great', 'book']: 
                        is_book_move = True
                    
                    if is_book_move:
                        classification = "book"
                        label = "Book Move"
                    else:
                        book_active = False # Chain Broken

                # Coach Reason
                reason = analyzer.generate_coach_reason(
                    classification, 
                    result['material_delta'], 
                    result['is_mate_threat'], 
                    result['eval_loss'], 
                    result['best_line'], 
                    result['is_check']
                )

                # Update Stats
                if classification in stats[turn]:
                    stats[turn][classification] += 1
                
                # Accuracy approximation
                acc = max(0, 100 * math.exp(-0.005 * result['normalized_loss']))
                acc_totals[turn] += acc
                move_counts[turn] += 1
                
                # Push Move to get resulting FEN
                board.push(move)

                # Result Object
                analysis_results.append({
                    'move_uci': move_uci,
                    'move_san': move_san,
                    'best_move': result['best_move'],
                    'rating': classification,
                    'score': f"{result['eval_after']/100:.2f}",
                    'reason': reason,
                    'square': move_uci[2:4],
                    'fen': board.fen(), 
                    'turn': turn,
                    'label': label,
                    'best_line': result['best_line']
                })
                
                # Opening Detection
                if board.fullmove_number <= 15:
                    op = detect_opening(board)
                    if op: detected_opening = op

            # Fix FENs in results:
            # We captured FEN *before* pushing in the loop above? No, I pushed after appending results.
            # Rereading my code above:
            #   move_san = ...
            #   analyze...
            #   append results (board.fen() is still BEFORE move here)
            #   board.push(move)
            # 
            # Original server.py:
            #   move_san = board.san(move)
            #   board.push(move)  <-- BEFORE appending results
            #   ...
            #   analysis_results.append({ ... 'fen': board.fen() ... })
            #
            # So I need to push before getting FEN for the result object?
            # Actually, `analyze_move` needs the board BEFORE the move.
            # So the flow:
            #   1. analyze(board_before)
            #   2. board.push(move)
            #   3. capture result with board.fen() (which is now after)
            
            # Let's correcting the loop logic in the replacement content.

        w_acc = round(acc_totals['w'] / move_counts['w']) if move_counts['w'] else 0
        b_acc = round(acc_totals['b'] / move_counts['b']) if move_counts['b'] else 0

        # Opening Info
        opening_name = game.headers.get("Opening", "Unknown Opening")
        eco_code = game.headers.get("ECO", "")

        if not opening_name or opening_name == "Unknown Opening" or opening_name == "?":
            if detected_opening:
                eco_code, opening_name = detected_opening

        return jsonify({
            'status': 'success',
            'analysis_data': analysis_results,
            'stats': stats,
            'match_accuracy': {'w': w_acc, 'b': b_acc},
            'players': {'white': white_player, 'black': black_player},
            'opening': {'name': opening_name, 'eco': eco_code}
        })

    except Exception as e:
        print(f"Server Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
