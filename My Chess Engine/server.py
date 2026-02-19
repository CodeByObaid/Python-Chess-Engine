import os
import io
import math
import chess
import chess.engine
import chess.pgn
import requests
from flask import Flask, jsonify, request, render_template
from openings import detect_opening
from analyzer import (
    analyze_moves_for_position, 
    EngineEval, 
    Config, 
    move_analysis_to_json,
    MoveAnalysis
)
# Use existing BookManager from book.py but wrap it if needed
from book import BookManager as LegacyBookManager

app = Flask(__name__)

# Configuration
ENGINE_PATH = os.path.join(os.path.dirname(__file__), "stockfish.exe")

if not os.path.exists(ENGINE_PATH):
    print(f"WARNING: Stockfish not found at {ENGINE_PATH}")

# --- Adapters ---

class ServerEngineInterface:
    def __init__(self, engine, depth=10):
        self.engine = engine
        self.default_depth = depth
        self.returns_white_pov = True # Standard UCI behavior (cp is white's perspective)

    def evaluate(self, board: chess.Board, depth: int):
        # Synchronous analysis
        info = self.engine.analyse(board, chess.engine.Limit(depth=depth))
        score = info["score"].white()
        
        cp = None
        mate = None
        
        if score.is_mate():
            mate = score.mate()
        else:
            cp = score.score()
            
        return {'cp': cp, 'mate': mate}

class ServerBookManager:
    def __init__(self):
        self.legacy_mgr = LegacyBookManager()
        
    def in_book(self, fen: str, move_uci: str) -> bool:
        # Use legacy manager which expects board
        board = chess.Board(fen)
        
        # Limit to 5 moves as requested
        if board.fullmove_number > 5:
            return False
            
        # Old manager limits to 20 moves internally
        return self.legacy_mgr.is_book_move(board, move_uci)
        
    def book_meta(self, fen: str, move_uci: str):
        return {} # Not supported by legacy yet

# --- Helpers ---

def generate_coach_reason(ma: MoveAnalysis) -> str:
    """Generates a coach explanation based on MoveAnalysis."""
    cls = ma.classification.lower()
    
    if cls == 'brilliant':
        return "You sacrificed material to win the game!"
    if cls == 'great':
        return "A great finding!"
    if cls == 'book':
        if ma.analysis_meta.get('book_health') == 'dubious':
             return f"Book move, but looks dubious ({ma.analysis_meta.get('engine_classification')} by engine)."
        return "Standard book move."
    if cls == 'best':
        if ma.win_delta == 0 and ma.is_forced:
            return "The only legal move."
        return "Excellent! Finding the optimal path."
    if cls == 'excellent':
        return "A very strong move."
    if cls == 'good':
        return "A solid move."
    if cls == 'inaccuracy':
        return "A slightly passive move."
    if cls == 'mistake':
        return "There was a much better move available."
    if cls == 'blunder':
        if ma.is_mate_missed: return "You missed a forced mate sequence."
        if ma.is_mate_threat: return "This move allows a forced mate."
        return "This move gives up a significant advantage."
        
    return "A move."

def _get_absolute_score(ma: MoveAnalysis, turn: str) -> str:
    """Returns the score in White Perspective for the frontend."""
    # Check for mate
    # If it's a huge value, format as M<num>
    val = ma.cp_after
    if val is None: return "0.0" # Should not happen if analyzer works
    
    abs_val = val
    if turn == 'b':
        abs_val = -val # Flip to White POV
        
    # Check Mate
    if abs(abs_val) > 20000:
        # It's a mate score.
        # 30000 - distance?
        # Analyzer uses 30000 for win.
        # But distance info is lost in pure CP? 
        # Analyzer's `mate` field from EngineEval is what we want?
        # But we only have `ma.cp_after`.
        # However, 30000 usually means Mate.
        # Let's just say M1.
        if abs_val > 0: return "M1"
        else: return "-M1"
        
    return f"{abs_val / 100.0:.2f}"

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch_games', methods=['POST'])
def fetch_games():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        if not username: 
            return jsonify({'status': 'error', 'message': 'Username required'})

        headers = {'User-Agent': 'Chess Game Review System (by Obaid Ur Rehman)'}
        
        # Get Archives
        archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
        resp = requests.get(archives_url, headers=headers, timeout=10)
        
        if resp.status_code != 200: 
            return jsonify({'status': 'error', 'message': f'User {username} not found (Status: {resp.status_code})'})
        
        archives = resp.json().get('archives', [])
        if not archives:
            return jsonify({'status': 'error', 'message': 'No game archives found'})

        # Get Games from Latest Archive
        latest_url = archives[-1]
        games_resp = requests.get(latest_url, headers=headers, timeout=10)
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
                'date': g.get('end_time')
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
        
        white_player = game.headers.get("White", "White")
        black_player = game.headers.get("Black", "Black")
        
        analysis_results = []
        stats = {k: {
            'brilliant':0, 'great':0, 'critical':0, 'best':0, 'good':0, 
            'book':0, 'inaccuracy':0, 'mistake':0, 'miss':0, 'blunder':0
        } for k in ['w', 'b']}
        
        acc_totals = {'w': 0, 'b': 0}
        move_counts = {'w': 0, 'b': 0}
        detected_opening = None
        
        # Initialize Book Manager
        book_manager = ServerBookManager()

        with chess.engine.SimpleEngine.popen_uci(ENGINE_PATH) as engine:
            engine_interface = ServerEngineInterface(engine, depth=12)
            
            # Initial Eval
            # We need eval BEFORE the first move to start the chain
            # But analyzer.py takes 'eval_before'.
            # Let's compute it for startpos.
            info = engine.analyse(board, chess.engine.Limit(depth=12))
            score = info["score"].white()
            cp = score.score() if not score.is_mate() else None
            mate = score.mate() if score.is_mate() else None
            
            # Material before (startpos)
            # Analyzer can calculate fallback, so we pass empty dictionary if lazy
            current_eval = EngineEval(cp=cp, mate=mate, material={})
            
            for move in game.mainline_moves():
                turn = 'w' if board.turn == chess.WHITE else 'b'
                move_uci = move.uci()
                move_san = board.san(move)
                
                # 1. Get Legal Moves Data (MultiPV)
                # We run MultiPV=3 to get the top moves.
                # If the user's move is not in the top 3, we analyze it specifically.
                
                info_multipv = engine.analyse(board, chess.engine.Limit(depth=10), multipv=3)
                # Output is list of dicts if multipv > 1
                if not isinstance(info_multipv, list): info_multipv = [info_multipv]
                
                # Check if user move is in MultiPV
                user_move_found = False
                for pv in info_multipv:
                    if "pv" in pv and pv["pv"][0] == move:
                        user_move_found = True
                        break
                
                # If user move not in top 3, analyze it specifically
                if not user_move_found:
                    # Analyze specifically this move
                    # We can't easily force "analyze just `move`" in python-chess without `root_moves`.
                    extra_info = engine.analyse(board, chess.engine.Limit(depth=10), root_moves=[move])
                    info_multipv.append(extra_info)

                # Construct legal_moves_data
                legal_moves_data = []
                
                rank_counter = 0
                for i, info_entry in enumerate(info_multipv):
                    if "pv" not in info_entry: continue
                    pv_move = info_entry["pv"][0]
                    
                    # Convert score
                    sc = info_entry["score"].white()
                    cp_val = sc.score() if not sc.is_mate() else None
                    mate_val = sc.mate() if sc.is_mate() else None
                    
                    # Material snapshot (expensive to do for all? Analyzer handles fallback)
                    # We'll let analyzer handle fallback for speed
                    
                    legal_moves_data.append({
                        'move_uci': pv_move.uci(),
                        'move_san': board.san(pv_move),
                        'engine_rank': i, # approximate
                        'engine_eval_after': {'cp': cp_val, 'mate': mate_val, 'depth': info_entry.get("depth")},
                        'is_capture': board.is_capture(pv_move),
                        'is_check': board.gives_check(pv_move),
                        'is_forced': False # We act as if not forced unless we pass all moves
                    })

                # Call Analyzer
                # Side to move?
                side_white = (board.turn == chess.WHITE)
                
                results = analyze_moves_for_position(
                    fen=board.fen(),
                    side_to_move_white=side_white,
                    eval_before=current_eval,
                    legal_moves_data=legal_moves_data,
                    book_manager=book_manager,
                    engine_interface=engine_interface,
                    config=Config()
                )
                
                # Find the result for the move played
                played_result = next((r for r in results if r.move_uci == move_uci), None)
                
                if not played_result:
                    # Should not happen if we ensured user move was analyzed
                    # Fallback
                    played_result = results[0] # Should not happen
                    
                # Store output
                ma_json = move_analysis_to_json(played_result)
                reason = generate_coach_reason(played_result)
                
                # Update Stats
                cls = played_result.classification.lower()
                if cls in stats[turn]:
                    stats[turn][cls] += 1
                
                acc_totals[turn] += played_result.accuracy
                move_counts[turn] += 1
                
                # Update loop state
                move_data_entry = next((m for m in legal_moves_data if m['move_uci'] == move_uci), None)
                if move_data_entry:
                    next_eval_dict = move_data_entry['engine_eval_after']
                    current_eval = EngineEval(
                        cp=next_eval_dict.get('cp'), 
                        mate=next_eval_dict.get('mate'),
                        material={} # Let analyzer recalc
                    )
                else:
                    current_eval = EngineEval(cp=0) # Should not happen

                board.push(move)
                
                # Formatting for Frontend
                analysis_results.append({
                    'move_uci': move_uci,
                    'move_san': move_san,
                    'best_move': played_result.analysis_meta.get("best_move_uci") or results[0].move_uci, 
                    'best_move_uci': next((r.move_uci for r in results if r.engine_rank == 0), ""),
                    'rating': cls,
                    'score': _get_absolute_score(played_result, turn),
                    'reason': reason,
                    'square': move_uci[2:4],
                    'fen': board.fen(), 
                    'turn': turn,
                    'label': ma_json['frontend_icon'], # or label text
                    'best_line': "", 
                })
                
                # Opening Detection
                if board.fullmove_number <= 15:
                    op = detect_opening(board)
                    if op: detected_opening = op

        w_acc = round(acc_totals['w'] / move_counts['w']) if move_counts['w'] else 0
        b_acc = round(acc_totals['b'] / move_counts['b']) if move_counts['b'] else 0

        opening_name = game.headers.get("Opening", "Unknown Opening")
        eco_code = game.headers.get("ECO", "")

        if not opening_name or opening_name in ["Unknown Opening", "?"]:
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
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
