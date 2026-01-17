import chess
import chess.engine
import math

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
        """Converts a chess.engine.Score object to centipawns."""
        if score_obj.is_mate():
            # Mate scores are high values, positive for winning, negative for losing
            return 10000 - (abs(score_obj.mate()) * 100) if score_obj.mate() > 0 else -10000 + (abs(score_obj.mate()) * 100)
        return score_obj.score()

    def count_material(self, board, color):
        """Counts material for a given color."""
        total = 0
        total += len(board.pieces(chess.PAWN, color)) * 1
        total += len(board.pieces(chess.KNIGHT, color)) * 3
        total += len(board.pieces(chess.BISHOP, color)) * 3
        total += len(board.pieces(chess.ROOK, color)) * 5
        total += len(board.pieces(chess.QUEEN, color)) * 9
        return total

    def get_phase(self, board):
        """Determines the game phase: Opening, Middlegame, Endgame."""
        # Simple heuristic based on piece count or fullmove number
        # A more robust one counts non-pawn material
        white_pieces = len(board.piece_map())
        if board.fullmove_number <= 10:
            return "Opening"
        
        # Count major/minor pieces
        w_mat = self.count_material(board, chess.WHITE) - len(board.pieces(chess.PAWN, chess.WHITE))
        b_mat = self.count_material(board, chess.BLACK) - len(board.pieces(chess.PAWN, chess.BLACK))
        
        if w_mat + b_mat <= 13: # Roughly 2 rooks + 1 minor piece each or less
            return "Endgame"
        
        return "Middlegame"

    def normalize_loss(self, loss, current_eval, is_mate_threat):
        """
        Normalizes eval loss based on position context.
        Position	Multiplier
        Eval ≤ ±0.5	×1.0
        Eval ≥ +3 or <= -3	×0.6
        Mate threats	×0.4
        """
        multiplier = 1.0
        abs_eval = abs(current_eval) / 100.0 # Convert cp to pawns for check

        if abs_eval >= 3.0:
            multiplier = 0.6
        elif is_mate_threat:
            multiplier = 0.4
        
        return loss * multiplier

    def analyze_move(self, board, move_uci, time_limit=0.1, depth_limit=18, engine=None):
        """
        Performs comprehensive analysis of a move.
        If 'engine' is provided, it uses that instance. Otherwise, it spawns a new one.
        """
        # If engine is passed, use it. Else, spawn a new one and ensure we quit it.
        local_engine = None
        if engine:
            search_engine = engine
        else:
            local_engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
            search_engine = local_engine

        try:
            # 1. Setup
            move = chess.Move.from_uci(move_uci)
            turn_color = board.turn
            
            # Metrics Before Move (MultiPV to find top moves and critical positions)
            # We use multipv=5 to get context on other candidate moves
            info_before = search_engine.analyse(board, chess.engine.Limit(time=time_limit, depth=depth_limit), multipv=5)
            
            # Parse MultiPV results
            # info_before is a list of dicts if multipv > 1, or a single dict if multipv=1 (but we requested 5)
            # python-chess usually returns a list for multipv > 1.
            pvs = info_before if isinstance(info_before, list) else [info_before]
            
            if not pvs:
                # Should not happen usually
                return {"error": "No analysis data"}

            best_score_obj = pvs[0]["score"].white()
            best_eval_white = self.get_score_value(best_score_obj)
            
            # Determine Top_moves_count (moves within 30 cp of best)
            top_moves_count = 0
            second_best_eval_white = None
            
            for i, pv in enumerate(pvs):
                score = self.get_score_value(pv["score"].white())
                diff = abs(best_eval_white - score)
                if diff <= 30:
                    top_moves_count += 1
                
                if i == 1:
                    second_best_eval_white = score

            # Best move from engine perspective
            best_move_uci = pvs[0]["pv"][0].uci() if "pv" in pvs[0] else None

            # Best Line SAN
            try:
                best_line_san = board.variation_san(pvs[0].get("pv", [])[:5])
            except:
                best_line_san = ""
            
            # Material Before
            mat_before = self.count_material(board, turn_color)
            
            # 2. Make Move
            is_capture = board.is_capture(move)
            is_check = board.gives_check(move)
            board.push(move)
            
            # 3. Metrics After Move
            # We analyze the new position to see the 'truth' of the played move
            info_after = search_engine.analyse(board, chess.engine.Limit(time=time_limit, depth=depth_limit))
            score_after_obj = info_after["score"].white()
            eval_after_white = self.get_score_value(score_after_obj)
            
            mat_after = self.count_material(board, turn_color)
            material_delta = mat_after - mat_before 
            
            # 4. Calculate Deltas
            if turn_color == chess.WHITE:
                eval_loss = best_eval_white - eval_after_white
                eval_before = best_eval_white
                eval_after = eval_after_white
                # For White, lower eval is worse. 
                # If second best is much worse, it means the best move was critical.
                # Criticality check: Best Eval - Second Best Eval
                criticality = (best_eval_white - second_best_eval_white) if second_best_eval_white is not None else 0
            else:
                eval_loss = eval_after_white - best_eval_white
                eval_before = best_eval_white
                eval_after = eval_after_white
                # For Black, higher eval is worse.
                # Criticality: Second Best - Best (since Best is lower)
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
                move_rank = 6 # Outside top 5
            
            # Phase
            phase = self.get_phase(board)
            
            # Is Forced? (Simple check: only 1 legal move or recapture)
            # We need to check legal moves count from BEFORE the move.
            board.pop() # Go back
            legal_moves_count = board.legal_moves.count()
            is_forced = (legal_moves_count == 1) or (is_capture and eval_loss < 50) # Heuristic
            # board.push(move) # REMOVED: Keep board popped so caller receives original state
            
            # Classify
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
                      is_forced, is_capture, move_number, phase, criticality, is_mate_threat):
        
        # 1. Brilliant (!!)
        # Rules: Rank <= 2, Material <= -3, Top_moves <= 2, Criticality >= 150, Depth >= 18, Not forced
        # Also Eval_after >= Eval_before (meaning we didn't lose evaluation significantly, actually Eval_loss check covers this)
        if (move_rank <= 2 and 
            material_delta <= -3 and 
            top_moves_count <= 2 and 
            criticality >= 150 and 
            not is_forced and 
            eval_loss <= 30):
            return "brilliant"

        # 2. Great Move (!)
        # Rules: Rank <= 3, Eval gain >= 120 (This is tricky, let's use Criticality or just good move with high impact?), Non-obvious
        # User says "Eval gain >= 120". This implies we found a move that is much better than others? 
        # Or maybe "Eval gain" means the position improved?
        # Let's interpret "Eval gain" as "This move is much better than the alternative" -> Criticality?
        # Or maybe it means we found a win where it looked like a draw?
        # Let's use: Rank <= 3, Criticality >= 120, Loss <= 10.
        if (move_rank <= 3 and criticality >= 120 and eval_loss <= 10 and not is_forced):
            return "great"

        # 3. Critical Move
        # Rules: Top_moves_count = 1, All other moves lose >= 200 (Criticality >= 200)
        if (top_moves_count == 1 and criticality >= 200 and eval_loss <= 50):
            return "critical" # Custom label, might map to Best or Great in UI

        # 4. Best Move
        if move_rank == 1 and eval_loss <= 10:
            return "best"

        # 5. Book
        if phase == "Opening" and move_number <= 10 and eval_loss <= 25:
            return "book"

        # 6. Good
        if normalized_loss <= 40:
            return "good"

        # 7. Inaccuracy
        if 40 < normalized_loss <= 90:
            return "inaccuracy"

        # 8. Mistake
        if 90 < normalized_loss <= 250:
            return "mistake"

        # 9. Blunder
        # Rules: Loss > 250 OR Forced mate appears OR Material loss >= 3
        # Note: Material_delta is (My After - My Before). If I lost material, delta is negative.
        # So Material loss >= 3 means Material_delta <= -3 (and no compensation, i.e., high loss).
        if (normalized_loss > 250 or 
            (material_delta <= -3 and normalized_loss > 100) or # Lost material without compensation
            (is_mate_threat and normalized_loss > 100)): # Mate threat appeared and we are losing
            return "blunder"

        # 10. Miss
        # Best/Critical existed, Played move <= Good, Eval swing >= 150
        # If we are here, it's likely a Miss if loss is high but not a blunder?
        # Actually, Miss is usually when we missed a win.
        # If Criticality was high (we had a win) and we played a move with high loss.
        if criticality >= 150 and normalized_loss > 100:
             return "miss"

        return "good" # Fallback
