import chess
import chess.engine

class MoveAnalyzer:
    def __init__(self, engine_path):
        self.engine_path = engine_path

    def generate_coach_reason(self, classification, material_delta, is_mate_threat, eval_loss, best_line_san, is_check):
        """Generates a coach explanation for the move."""
        if classification == 'brilliant':
            return "You sacrificed material for a winning attack!"
        if classification == 'great':
            return "A great finding!"
        if classification == 'critical':
             return "You found the only move that saves the position!"
        if classification == 'blunder':
            if is_mate_threat: return "You missed a forced mate sequence."
            if material_delta <= -3: return "You hung a piece!"
            return "This move gives up a significant advantage."
        if classification == 'mistake':
            return "There was a much better move available."
        if classification == 'miss':
            return "You missed a winning opportunity."
        if classification == 'best':
            return "Excellent! Finding the optimal path."
        if classification == 'book':
            return "Standard book move."
        if classification == 'inaccuracy':
            return "A slightly passive move."
        if material_delta >= 3:
            return "You won material!"
        if is_check:
            return "Delivering check."
        
        return "A solid move."

    def get_score_value(self, score_obj):
        if score_obj.is_mate():
            return 10000 - (abs(score_obj.mate()) * 100) if score_obj.mate() > 0 else -10000 + (abs(score_obj.mate()) * 100)
        return score_obj.score()

    def count_material(self, board, color):
        total = 0
        total += len(board.pieces(chess.PAWN, color)) * 1
        total += len(board.pieces(chess.KNIGHT, color)) * 3
        total += len(board.pieces(chess.BISHOP, color)) * 3
        total += len(board.pieces(chess.ROOK, color)) * 5
        total += len(board.pieces(chess.QUEEN, color)) * 9
        return total

    def get_phase(self, board):
        white_pieces = len(board.piece_map())
        if board.fullmove_number <= 10:
            return "Opening"
        
        w_mat = self.count_material(board, chess.WHITE) - len(board.pieces(chess.PAWN, chess.WHITE))
        b_mat = self.count_material(board, chess.BLACK) - len(board.pieces(chess.PAWN, chess.BLACK))
        
        if w_mat + b_mat <= 13: 
            return "Endgame"
        
        return "Middlegame"

    def normalize_loss(self, loss, current_eval, is_mate_threat):
        multiplier = 1.0
        abs_eval = abs(current_eval) / 100.0 

        if abs_eval >= 3.0:
            multiplier = 0.6
        elif is_mate_threat:
            multiplier = 0.4
        
        return loss * multiplier

    def get_material_balance(self, board):
        white = self.count_material(board, chess.WHITE)
        black = self.count_material(board, chess.BLACK)
        return white - black

    def analyze_move(self, board, move_uci, time_limit=0.1, depth_limit=18, engine=None):
        local_engine = None
        if engine:
            search_engine = engine
        else:
            local_engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
            search_engine = local_engine

        try:
            # Setup board and turn info
            move = chess.Move.from_uci(move_uci)
            turn_color = board.turn
            
            # Record starting material balance (Relative to mover)
            start_balance = self.get_material_balance(board)
            if turn_color == chess.BLACK:
                start_balance = -start_balance

            # Get engine metrics before the move
            info_before = search_engine.analyse(board, chess.engine.Limit(time=time_limit, depth=depth_limit), multipv=5)
            pvs = info_before if isinstance(info_before, list) else [info_before]
            
            if not pvs:
                return {"error": "No analysis data"}

            best_score_obj = pvs[0]["score"].white()
            best_eval_white = self.get_score_value(best_score_obj)
            
            # Count how many moves are "good" (within a threshold)
            top_moves_count = 0
            second_best_eval_white = None
            
            for i, pv in enumerate(pvs):
                score = self.get_score_value(pv["score"].white())
                diff = abs(best_eval_white - score)
                if diff <= 30:
                    top_moves_count += 1
                
                if i == 1:
                    second_best_eval_white = score

            best_move_uci = pvs[0]["pv"][0].uci() if "pv" in pvs[0] else None

            try:
                best_line_san = board.variation_san(pvs[0].get("pv", [])[:5])
            except:
                best_line_san = ""
            
            # Execute move to analyze resulting position
            is_capture = board.is_capture(move)
            is_check = board.gives_check(move)
            board.push(move)
            
            # Get metrics after the move
            info_after = search_engine.analyse(board, chess.engine.Limit(time=time_limit, depth=depth_limit))
            score_after_obj = info_after["score"].white()
            eval_after_white = self.get_score_value(score_after_obj)
            
            # Check projected material balance (Simulate PV)
            temp_board = board.copy()
            pv_moves = info_after.get("pv", [])
            # Look ahead up to 6 plies (3 full moves) to catch recaptures
            for pv_move in pv_moves[:6]:
                temp_board.push(pv_move)
            
            end_balance = self.get_material_balance(temp_board)
            if turn_color == chess.BLACK:
                end_balance = -end_balance
            
            material_delta = end_balance - start_balance
            
            # Calculate evaluation changes
            if turn_color == chess.WHITE:
                eval_loss = best_eval_white - eval_after_white
                eval_before = best_eval_white
                eval_after = eval_after_white
                criticality = (best_eval_white - second_best_eval_white) if second_best_eval_white is not None else 0
            else:
                eval_loss = eval_after_white - best_eval_white
                eval_before = best_eval_white
                eval_after = eval_after_white
                criticality = (second_best_eval_white - best_eval_white) if second_best_eval_white is not None else 0
            
            if eval_loss < 0: eval_loss = 0
            if criticality < 0: criticality = 0

            # Normalize
            is_mate_threat = score_after_obj.is_mate()
            normalized_loss = self.normalize_loss(eval_loss, eval_before, is_mate_threat)
            
            # Move Rank
            move_rank = 1
            for i, pv in enumerate(pvs):
                pv_move = pv["pv"][0].uci() if "pv" in pv else None
                if pv_move == move_uci:
                    move_rank = i + 1
                    break
            else:
                move_rank = 6
            
            phase = self.get_phase(board)
            
            # Is Forced?
            board.pop() 
            legal_moves_count = board.legal_moves.count()
            is_strictly_forced = (legal_moves_count == 1)
            is_forced = is_strictly_forced or (is_capture and eval_loss < 50)
            
            classification = self.classify_move(
                move_rank=move_rank,
                eval_loss=eval_loss,
                normalized_loss=normalized_loss,
                material_delta=material_delta,
                eval_before=eval_before,
                eval_after=eval_after,
                top_moves_count=top_moves_count,
                depth_required=depth_limit,
                is_forced=is_forced,
                is_strictly_forced=is_strictly_forced,
                is_capture=is_capture,
                move_number=board.fullmove_number,
                phase=phase,
                criticality=criticality,
                is_mate_threat=is_mate_threat
            )
            
            return {
                "eval_before": eval_before,
                "eval_after": eval_after,
                "eval_loss": eval_loss,
                "normalized_loss": normalized_loss,
                "move_rank": move_rank,
                "material_delta": material_delta,
                "classification": classification,
                "best_move": best_move_uci,
                "top_moves_count": top_moves_count,
                "criticality": criticality,
                "is_mate_threat": is_mate_threat,
                "is_check": is_check,
                "best_line": best_line_san
            }
            
        finally:
            if local_engine:
                local_engine.quit()

    def classify_move(self, move_rank, eval_loss, normalized_loss, material_delta, 
                      eval_before, eval_after, top_moves_count, depth_required, 
                      is_forced, is_capture, move_number, phase, criticality, 
                      is_mate_threat, is_strictly_forced=False):
        
        # Brilliant
        
        if (move_rank == 1 and 
            material_delta <= -1 and 
            eval_loss <= 20 and
            not is_strictly_forced):
            return "brilliant"

        # Great
        if (move_rank <= 2 and criticality >= 100 and eval_loss <= 15 and not is_forced):
            return "great"

        # Critical
        if (top_moves_count == 1 and criticality >= 200 and eval_loss <= 50):
            return "critical"

        # Best
        if move_rank == 1 and eval_loss <= 15:
            return "best"

        # Book
        if phase == "Opening" and move_number <= 10 and eval_loss <= 25:
            return "book"

        # Good
        if normalized_loss <= 40:
            return "good"

        # Inaccuracy
        if 40 < normalized_loss <= 90:
            return "inaccuracy"

        # Mistake
        if 90 < normalized_loss <= 250:
            return "mistake"

        # Blunder
        if (normalized_loss > 250 or 
            (material_delta <= -3 and normalized_loss > 100) or 
            (is_mate_threat and normalized_loss > 100)): 
            return "blunder"

        # Miss
        if criticality >= 150 and normalized_loss > 100:
             return "miss"

        return "good" 
