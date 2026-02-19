"""
Chess Move Analyzer Module
==========================

A robust, thread-safe, synchronous module for analyzing chess positions and moves.
It classifies moves (Brilliant, Best, Blunder, etc.), computes accuracy scores,
and ensures strict adherence to business rules regarding sacrifices, book moves,
and engine evaluation normalization.
"""

import math
import uuid
import logging
import chess
from dataclasses import dataclass, field, replace
from typing import List, Optional, Dict, Any, Protocol, Union

# --- Configuration & Constants ---

@dataclass
class Config:
    # Sigmoid Win Probability Key
    sigmoid_k: float = 0.00368
    
    # Mate Handling
    mate_win_score: float = 100.0
    mate_loss_score: float = 0.0
    mate_cp_base: int = 10000
    mate_cp_step: int = 100

    # Piece Values (Pawn-Equivalent)
    piece_values: Dict[int, int] = field(default_factory=lambda: {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 0
    })

    # Sacrifice Thresholds
    # Sacrifice Thresholds
    big_sacrifice_cp: int = 210  # Reduced to catch Knight sacs (e.g. Fried Liver)
    
    pawn_sacrifice_cp: int = 90
    sacrifice_sound_max_win_loss: float = 5.0  # %

    # Tie Thresholds
    tie_cp_eps: int = 10
    tie_win_eps: float = 0.7

    # Classification Win Deltas (Lower bounds for classification buckets)
    # Best: < 1%, Excellent: < 3%, etc.
    delta_best: float = 1.0
    delta_excellent: float = 3.0
    delta_good: float = 5.0
    delta_inaccuracy: float = 9.0
    delta_mistake: float = 20.0
    # Blunder is > 20.0
    
    # Book
    book_dubious_threshold: float = 2.0 # Stricter to catch Nxd5?
    
    # Stability
    unstable_cp_diff: int = 200
    
    # Material Penalty Configuration
    material_penalty_factor: float = 0.8
    
    # Engine verification
    verification_depth_extra: int = 4


DEFAULT_CONFIG = Config()
logger = logging.getLogger(__name__)


# --- Data Models ---

@dataclass
class EngineEval:
    """Raw evaluation data from the engine."""
    cp: Optional[int] = None
    mate: Optional[int] = None
    material: Optional[Dict[str, int]] = None
    depth: Optional[int] = None


@dataclass
class MoveAnalysis:
    """Complete analysis result for a single move."""
    analysis_id: str
    move_uci: str
    move_san: Optional[str]
    engine_rank: int  # 0-indexed best
    
    # Evals
    cp_before: Optional[int]
    cp_after: Optional[int]
    win_before: float
    win_after: float
    win_delta: float  # Positive = worse for player
    
    # Material
    material_before_cp: Optional[int]
    material_after_cp: Optional[int]
    material_delta_cp: Optional[int]
    non_pawn_piece_loss: Optional[int]
    
    # Flags
    is_capture: bool
    is_promotion: bool
    is_castle: bool
    is_check: bool
    is_forced: bool
    is_book_move: bool
    is_mate_threat: bool # Opponent has forced mate
    is_mate_missed: bool # We missed a forced mate
    
    # Results
    classification: str
    accuracy: int  # 0-100
    classification_confidence: str  # high/medium/low
    comments: Optional[str] = None
    analysis_meta: Dict[str, Any] = field(default_factory=dict)


# --- Interfaces (Protocols) ---

class EngineInterface(Protocol):
    default_depth: int
    returns_white_pov: bool
    
    def evaluate(self, board: chess.Board, depth: int) -> Dict[str, Optional[int]]:
        """Returns {'cp': int|None, 'mate': int|None}"""
        ...

class BookManager(Protocol):
    def in_book(self, fen: str, move_uci: str) -> bool:
        ...
        
    def book_meta(self, fen: str, move_uci: str) -> Optional[Dict[str, Any]]:
        ...


# --- Core Helper Functions ---

def normalize_cp(engine_cp: Optional[int], engine_returns_white_pov: bool, side_to_move_white: bool) -> Optional[int]:
    """
    Normalizes CP to be relative to the side to move.
    Positive CP means advantage for the side to move.
    """
    if engine_cp is None:
        return None
    
    if engine_returns_white_pov:
        return engine_cp if side_to_move_white else -engine_cp
    else:
        # Engine already returns side-to-move relative CP? 
        # CAUTION: Most UCI engines return score relative to side-to-move, 
        # but python-chess Score objects might be absolute or relative depending on how used.
        # The prompt implies engine_interface might have a flag `returns_white_pov`.
        # Adhering to prompt spec:
        return engine_cp

def mate_to_cp_equiv(mate: int, config: Config) -> int:
    """
    Converts a mate score (mate in X moves) to a large CP-equivalent integer for sorting.
    Positive mate (win) -> very large positive CP.
    Negative mate (loss) -> very large negative CP.
    """
    if mate == 0:
        return 0 # Should ideally use is_checkmate check instead, but handled here.
        
    sign = 1 if mate > 0 else -1
    return sign * (config.mate_cp_base - abs(mate) * config.mate_cp_step)

def cp_to_win_percent(cp: int, config: Config) -> float:
    """Calculates win probability [0, 100] from centipawns using sigmoid."""
    return 100.0 / (1.0 + math.exp(-config.sigmoid_k * cp))

def compute_material_cp(material_counts: Dict[str, int], config: Config) -> int:
    """Computes total material value in centipawns from a count dictionary."""
    total = 0
    
    symbol_map = {
        'P': chess.PAWN, 'N': chess.KNIGHT, 'B': chess.BISHOP, 
        'R': chess.ROOK, 'Q': chess.QUEEN, 'K': chess.KING
    }
    
    for piece_char, count in material_counts.items():
        p_type = symbol_map.get(piece_char.upper())
        if p_type is not None:
            total += count * config.piece_values.get(p_type, 0)
            
    return total

def scale_by_position(win_before: float) -> float:
    if 45 <= win_before <= 55:
        return 1.4
    elif (35 <= win_before < 45) or (55 < win_before <= 65):
        return 1.1
    elif win_before < 20 or win_before > 80:
        return 0.6
    return 1.0


# --- Main Analysis Function ---

def analyze_moves_for_position(
    fen: str,
    side_to_move_white: bool,
    eval_before: EngineEval,
    legal_moves_data: List[Dict[str, Any]],
    book_manager: BookManager,
    engine_interface: EngineInterface,
    config: Optional[Config] = None
) -> List[MoveAnalysis]:
    """
    Analyzes all legal moves for a given position.
    
    Args:
        fen: FEN string of the position BEFORE the move.
        side_to_move_white: True if it's White's turn.
        eval_before: Engine evaluation of the current position.
        legal_moves_data: List of data for each legal move.
        book_manager: Interface for opening book lookups.
        engine_interface: Interface for engine calculations.
        config: Configuration options (uses default if None).
        
    Returns:
        List of MoveAnalysis objects.
    """
    if config is None:
        config = DEFAULT_CONFIG

    analysis_id_base = str(uuid.uuid4())
    logger.debug(f"[{analysis_id_base}] Starting analysis for FEN: {fen}")
    logger.debug(f"[{analysis_id_base}] Side: {'White' if side_to_move_white else 'Black'}, Legal moves: {len(legal_moves_data)}")

    # 1. Process Eval Before
    # ----------------------
    cp_val_before = normalize_cp(eval_before.cp, engine_interface.returns_white_pov, side_to_move_white)
    
    # Handle mate before
    if eval_before.mate is not None:
        # Normalize mate like in loop
        mate_val_before = eval_before.mate
        if engine_interface.returns_white_pov and not side_to_move_white:
            mate_val_before = -mate_val_before

        if mate_val_before > 0:
            win_before = config.mate_win_score
            cp_val_before = mate_to_cp_equiv(mate_val_before, config)
        else:
            win_before = config.mate_loss_score
            cp_val_before = mate_to_cp_equiv(mate_val_before, config)
    else:
        # Standard CP
        if cp_val_before is None:
            # Fallback if engine returns nothing? (Should ensure inputs are valid)
            cp_val_before = 0
        win_before = cp_to_win_percent(cp_val_before, config)

    logger.debug(f"[{analysis_id_base}] Win Before: {win_before:.2f}% (CP: {cp_val_before})")

    # Board for verification/fallback
    board_master = chess.Board(fen)
    
    # Calculate material before if missing
    # We rely on specific piece counts if provided, otherwise compute from board
    if eval_before.material:
        material_before_cp = compute_material_cp(eval_before.material, config)
    else:
        # Fallback
        # Note: simplistic count of side's material
        # We need counts for the side to move to detect sacrifices made BY them
        pm = {}
        for pt in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            pm[chess.piece_symbol(pt).upper()] = len(board_master.pieces(pt, chess.WHITE if side_to_move_white else chess.BLACK))
        material_before_cp = compute_material_cp(pm, config)

    results: List[MoveAnalysis] = []
    
    # Pre-calculate forced status
    is_forced_position = (len(legal_moves_data) == 1)

    # First pass: Process raw data for all moves to find the engine best score
    # We need to identify tie-scores
    
    processed_moves = []
    
    best_move_cp_score = -float('inf')
    best_move_win_percent = -1.0
    
    # First pass processing loop
    for move_data in legal_moves_data:
        move_uci = move_data['move_uci']
        
        # Engine Eval After
        # Note: Engine eval for the position AFTER current move.
        # We need to ensure we have score from the Root Side's perspective.
        
        e_eval = move_data.get('engine_eval_after', {})
        raw_cp = e_eval.get('cp')
        raw_mate = e_eval.get('mate')
        
        # Normalize: ensure we have score from OUR perspective (Root Side)
        # If `engine_returns_white_pov` is true, and we are Black, we flip.
        # If `engine_returns_white_pov` is true, and we are White, we keep.
        
        current_cp = normalize_cp(raw_cp, engine_interface.returns_white_pov, side_to_move_white)
        
        if raw_mate is not None:
             # Mate logic
             # Normalize mate to current POV
             # If returns_white_pov is True:
             #    Positive mate = White wins.
             #    If side_to_move_white=True -> We win (+).
             #    If side_to_move_white=False -> White wins (We lose) (-).
             
             mate_val = raw_mate
             if engine_interface.returns_white_pov and not side_to_move_white:
                 mate_val = -mate_val
                 
             if mate_val > 0:
                 current_win = config.mate_win_score
                 current_cp = mate_to_cp_equiv(mate_val, config)
             else:
                 current_win = config.mate_loss_score
                 current_cp = mate_to_cp_equiv(mate_val, config)
        else:
             if current_cp is None: current_cp = 0 # Safety
             current_win = cp_to_win_percent(current_cp, config)
             
        # Track best
        if current_cp > best_move_cp_score:
            best_move_cp_score = current_cp
        if current_win > best_move_win_percent:
            best_move_win_percent = current_win
            
        processed_moves.append({
            'data': move_data,
            'cp': current_cp,
            'win': current_win
        })
        
    # Second Pass: Create Analysis Objects
    for entry in processed_moves:
        move_data = entry['data']
        cp_after = entry['cp']
        win_after = entry['win']
        move_uci = move_data['move_uci']
        
        # 1. Win Delta
        # ------------
        # Improvement (negative delta) is clamped to 0 usually, but let's keep raw delta?
        # Spec says: "positive = move lost win%"
        win_delta = win_before - win_after
        # Special case: Improvement logic? "win_delta < 0 => win_delta = 0"
        # Usually we treat improvements as 0 loss.
        # But if we were losing (-500cp) and found a swindle (0cp), win_delta is negative.
        # We generally clamp to 0 for classification purposes unless we want to track 'finding a win'.
        # For this spec, let's keep raw delta for accuracy calc unless specified.
        # "100 - abs(win_delta)..." implies magnitude matters.
        # But usually accuracy punishes BAD moves. Good moves are accurate.
        # Let's enforce non-negative loss for classification, but accuracy uses abs.
        
        effective_loss = max(0.0, win_delta)
        
        # 2. Rank & Ties
        # --------------
        # Check against best found in this batch
        is_tied_best = False
        if abs(cp_after - best_move_cp_score) <= config.tie_cp_eps:
            is_tied_best = True
        elif abs(win_after - best_move_win_percent) <= config.tie_win_eps:
            is_tied_best = True
            
        # Original rank from engine (0-indexed best?)
        # Spec says "engine_rank: int (0 = best)".
        # We should trust the input's engine_rank if provided, but override if tied.
        original_rank = move_data.get('engine_rank', 99)
        
        # 3. Material
        # -----------
        # Snapshot after
        mat_after_dict = move_data.get('material_after')
        if mat_after_dict:
            material_after_cp = compute_material_cp(mat_after_dict, config)
        else:
            # Fallback
            temp_board = board_master.copy()
            temp_board.push(chess.Move.from_uci(move_uci))
            pm = {}
            for pt in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
                pm[chess.piece_symbol(pt).upper()] = len(temp_board.pieces(pt, chess.WHITE if side_to_move_white else chess.BLACK))
            material_after_cp = compute_material_cp(pm, config)
            
        material_delta = material_after_cp - material_before_cp
        # Note: if we lost material, delta is negative.
        
        # Non-pawn piece loss check (rough)
        # We need counts.
        # Re-calc counts to be sure
        def count_pieces(m_dict):
            s = 0
            for k, v in m_dict.items():
                if k.upper() != 'P' and k.upper() != 'K':
                    s += v
            return s
            
        # Determine actual piece counts
        # (Ideally passed in snapshots, but we can infer from material dicts if fully populated)
        # Let's assume material dict inputs are reliable or we used fallback
        # Wait, if we used fallback 'pm', it's reliable.
        # If we accept inputs, we scan them.
        
        # Since we need rigorous piece loss count for Brilliant criteria:
        # "pieces_lost >= 2"
        # We should ensure we have piece counts.
        if eval_before.material and mat_after_dict:
            ct_before = count_pieces(eval_before.material)
            ct_after = count_pieces(mat_after_dict)
        else:
            # Re-count using python-chess to be safe and consistent
             # (Even if inefficient, it's safer)
             # Already did fallback logic for CPs.
             # Let's just use CP delta for primary decision as per spec:
             # "material_delta_cp <= -big_sacrifice_cp_threshold" covers most.
             # But "non_pawn_piece_loss" is a field.
             # Let's count properly.
             temp_board_before = board_master
             temp_board_after = temp_board_before.copy()
             temp_board_after.push(chess.Move.from_uci(move_uci))
             
             def count_non_pawns_on_board(b, color):
                 return sum(len(b.pieces(pt, color)) for pt in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN])
             
             c = chess.WHITE if side_to_move_white else chess.BLACK
             ct_before = count_non_pawns_on_board(temp_board_before, c)
             ct_after = count_non_pawns_on_board(temp_board_after, c)
        
        non_pawn_loss = ct_before - ct_after
        
        # 4. Book Check
        # -------------
        # Canonicalize FEN
        # python-chess board.fen() produces canonical FEN
        canonical_fen = board_master.fen()
        is_book = book_manager.in_book(canonical_fen, move_uci)
        book_meta = book_manager.book_meta(canonical_fen, move_uci) or {}
        
        # 5. Preliminary Classification (Brilliant/Great Candidates)
        # ----------------------------------------------------------
        classification = "Other"
        comments = []
        confidence = "low"
        stability = 0.5 # Default
        
        
        # Stability Check
        # We can implement stability checks here if multiple depth evals are provided.
        # For now, we rely on the input depth.
        
        analysis_meta = {}
        depth_input = move_data.get('engine_eval_after', {}).get('depth', 0)
        
        # Sacrifice Verification
        # ----------------------
        is_sac_candidate = False
        sac_type = None # "big" or "pawn"
        
        if is_tied_best and not is_forced_position:
            if material_delta <= -config.big_sacrifice_cp:
                is_sac_candidate = True
                sac_type = "Brilliant"
            elif material_delta <= -config.pawn_sacrifice_cp:
                is_sac_candidate = True
                sac_type = "Great"
            
            # Additional Check for En Prise / Trade Sacs
            if not is_sac_candidate:
                move_obj = chess.Move.from_uci(move_uci)
                if board_master.is_capture(move_obj):
                    victim_pt = board_master.piece_type_at(move_obj.to_square)
                    attacker_pt = board_master.piece_type_at(move_obj.from_square)
                    
                    if victim_pt and attacker_pt:
                        victim_val = config.piece_values.get(victim_pt, 0)
                        attacker_val = config.piece_values.get(attacker_pt, 0)
                        opp_color = not (board_master.turn)
                        
                        if board_master.is_attacked_by(opp_color, move_obj.to_square):
                            trade_delta = victim_val - attacker_val
                            if trade_delta <= -config.big_sacrifice_cp:
                                is_sac_candidate = True
                                sac_type = "Brilliant"
                            elif trade_delta <= -config.pawn_sacrifice_cp:
                                is_sac_candidate = True
                                sac_type = "Great"
                
        # Handle verification
        verified_sound = False
        is_unverified = False
        
        if is_sac_candidate and effective_loss < config.sacrifice_sound_max_win_loss:
            # It LOOKS sound on shallow eval. Verify!
            try:
                # Re-evaluate deeper
                logger.debug(f"[{analysis_id_base}] Verifying sacrifice for {move_uci}. Shallow delta: {effective_loss:.2f}")
                
                board_after = board_master.copy()
                board_after.push(chess.Move.from_uci(move_uci))
                
                # Check deeper
                verify_depth = engine_interface.default_depth + config.verification_depth_extra
                deep_eval = engine_interface.evaluate(board_after, depth=verify_depth)
                
                # Compute deep win
                d_cp = normalize_cp(deep_eval.get('cp'), engine_interface.returns_white_pov, side_to_move_white)
                d_mate = deep_eval.get('mate')
                
                if d_mate is not None:
                     # Normalize deep mate
                     d_mate_val = d_mate
                     if engine_interface.returns_white_pov and not side_to_move_white:
                         d_mate_val = -d_mate_val
                         
                     if d_mate_val > 0:
                         d_win = config.mate_win_score
                     else:
                         d_win = config.mate_loss_score
                else:
                    if d_cp is None: d_cp = 0
                    d_win = cp_to_win_percent(d_cp, config)
                    
                deep_delta = win_before - d_win
                if deep_delta < 0: deep_delta = 0 # Improvement
                
                if deep_delta < config.sacrifice_sound_max_win_loss:
                    verified_sound = True
                    logger.debug(f"[{analysis_id_base}] Verified Sound. Deep delta: {deep_delta:.2f}")
                else:
                    logger.debug(f"[{analysis_id_base}] Sacrifice refuted. Deep delta: {deep_delta:.2f}")
                    comments.append(f"Sacrifice unsound at depth {verify_depth} (loss {deep_delta:.1f}%)")
            
            except Exception as e:
                logger.error(f"Error checking sacrifice for {move_uci}: {e}")
                is_unverified = True
                comments.append("Verification failed")

        # 6. Classification Logic
        # -----------------------
        
        final_class = "Other"
        
        # Book logic first (but Brilliant overrides)
        
        is_brilliant_great = False
        
        if is_sac_candidate and verified_sound and not is_forced_position:
            final_class = sac_type # "Brilliant" or "Great"
            is_brilliant_great = True
        
        # "Great Find" Logic (Single Good Move)
        if not is_brilliant_great and not is_forced_position:
             # If we moved, and it was the ONLY good move.
             # Check if we are Best/Excellent (loss small)
             if effective_loss < config.delta_excellent:
                 # Check if next best move diff is large
                 # We need sorted processed_moves
                 sorted_moves = sorted(processed_moves, key=lambda x: x['win'], reverse=True)
                 if len(sorted_moves) > 1:
                     best_win = sorted_moves[0]['win']
                     second_win = sorted_moves[1]['win']
                     # If best move matches current move (win ~ win_after)
                     if abs(win_after - best_win) < 1.0: # We are top move
                         diff = best_win - second_win
                         if diff > 20.0 and best_win > 50.0:
                             final_class = "Great"
                             is_brilliant_great = True
                             comments.append("Found the only good move.")

        # Mate Flags
        # ----------
        is_mate_missed = False
        is_mate_threat = False
        
        # Did we miss a mate?
        # If we had mate before (mate > 0) and now we don't (mate <= 0 or None)
        # Note: eval_before.mate is raw engine output. We need to normalize?
        # normalize_cp handled CP. mate_val_before handles normalized mate.
        
        # Helper to check if a specific move result has mate
        # We need raw mate from move_data['engine_eval_after']
        raw_mate_after = move_data.get('engine_eval_after', {}).get('mate')
        
        # Normalize mate after
        normalized_mate_after = None
        if raw_mate_after is not None:
             m = raw_mate_after
             if engine_interface.returns_white_pov and not side_to_move_white:
                 m = -m
             normalized_mate_after = m
        
        if eval_before.mate is not None:
             # Check if we missed a win
             # mate_val_before was computed earlier (normalized)
             if mate_val_before > 0:
                 # We had a mate. Did we keep it?
                 if normalized_mate_after is None or normalized_mate_after <= 0:
                     is_mate_missed = True
                     
        # Did we allow a mate? (Opponent has mate)
        if normalized_mate_after is not None and normalized_mate_after < 0:
            is_mate_threat = True

        if not is_brilliant_great:
            # Order of precedence
            
            # Mate Preservation
            moves_mate_before = (eval_before.mate is not None and eval_before.mate > 0)
            moves_mate_after_preserves = (
                normalized_mate_after is not None and normalized_mate_after > 0
            ) 
            
            preserves_win_100 = (win_before > 99.0 and win_after > 99.0)
            
            # Forced?
            if is_forced_position:
                final_class = "Forced"
                comments.append("Only legal move.")
            
            # Book?
            elif is_book:
                # Check dubious
                if effective_loss > config.book_dubious_threshold:
                    # It's book but dubious.
                    # Degrade to engine class if it is worse than Inaccuracy (Mistake/Blunder)
                    eng_class = classify_by_delta(effective_loss, config)
                    analysis_meta['book_health'] = "dubious"
                    analysis_meta['engine_classification'] = eng_class
                    comments.append(f"Book (dubious): loses {effective_loss:.1f}%")
                    
                    if eng_class in ["Mistake", "Blunder"]:
                        final_class = eng_class
                    else:
                        final_class = "Book"
                else:
                    final_class = "Book"
                    analysis_meta['book_health'] = "ok"

            else:
                # Standard Engine Class
                # Check for "Best" (Tied moves)
                if is_tied_best:
                     final_class = "Best"
                elif preserves_win_100:
                     final_class = "Best" # effectively
                else:
                     final_class = classify_by_delta(effective_loss, config)
                     
                     # Adjustment for "Already Lost" / "Already Won"
                     # If win_before < 5.0 (Lost), don't call it Blunder just for dropping to 0.1
                     # But delta should be small anyway (5.0 -> 0.0 is delta 5).
                     # Delta 5 is Good/Inaccuracy.
                     # What if 5.0 -> -100 (if not clamped)??
                     # Clamped effective_loss handles it.
                     
                     if win_before < 5.0 and final_class in ["Blunder", "Mistake"]:
                         comments.append("Already lost")
        
        # 7. Accuracy Calculation
        # -----------------------
        # scale = scale_by_position(win_before)
        scale = scale_by_position(win_before)
        
        base_accuracy = 100.0 - (abs(win_delta) * scale)
        
        bonus = 2.0 if is_book else 0.0
        
        # Stability bonus
        # Assumes default 0.5, increases if depth is high and move is tied best.
        stability_val = 0.5
        if depth_input >= engine_interface.default_depth + 2:
            stability_val = 0.8
        elif depth_input < 10:
            stability_val = 0.2
            
        stability_bonus = int(5 * stability_val)
        
        # Material penalty
        mat_penalty = max(0, -material_delta / 100.0) * config.material_penalty_factor
        
        accuracy_raw = base_accuracy + bonus + stability_bonus - mat_penalty
        accuracy = int(max(0, min(100, round(accuracy_raw))))

        # 8. Confidence
        # -------------
        # "high" if stability >= 0.8 and depth >= default+2 and engine_rank == 0 (tier 1)
        conf_str = "low"
        if stability_val >= 0.8 and depth_input >= engine_interface.default_depth + 2 and is_tied_best:
            conf_str = "high"
        elif stability_val >= 0.5:
            conf_str = "medium"
            
        # 9. Assembly
        # -----------
        
        analysis_meta.update({
             "original_rank": original_rank,
             "is_sac_candidate": is_sac_candidate,
             "verified_sound": verified_sound
        })
        if is_sac_candidate:
             analysis_meta['sac_type'] = sac_type
             analysis_meta['verified'] = verified_sound
             
        # Add analysis object
        ma = MoveAnalysis(
            analysis_id=f"{analysis_id_base}-{move_uci}",
            move_uci=move_uci,
            move_san=move_data.get('move_san'),
            engine_rank=original_rank,
            cp_before=int(cp_val_before) if cp_val_before is not None else None,
            cp_after=int(cp_after) if cp_after is not None else None,
            win_before=win_before,
            win_after=win_after,
            win_delta=win_delta,
            material_before_cp=material_before_cp,
            material_after_cp=material_after_cp,
            material_delta_cp=material_delta,
            non_pawn_piece_loss=non_pawn_loss,
            is_capture=move_data.get('is_capture', False),
            is_promotion=move_data.get('is_promotion', False),
            is_castle=move_data.get('is_castle', False),
            is_check=move_data.get('is_check', False),
            is_forced=is_forced_position,
            is_book_move=is_book,
            is_mate_missed=is_mate_missed,
            is_mate_threat=is_mate_threat,
            classification=final_class,
            accuracy=accuracy,
            classification_confidence=conf_str,
            comments="; ".join(comments) if comments else None,
            analysis_meta=analysis_meta
        )
        
        results.append(ma)
        
        logger.debug(
            f"Move: {move_uci} | Rank: {original_rank} | Class: {final_class} | "
            f"WinDelta: {win_delta:.2f} | Acc: {accuracy}"
        )

    return results


def classify_by_delta(loss: float, config: Config) -> str:
    """Standard classification based on win% loss."""
    if loss <= config.delta_best:
        return "Best"
    if loss <= config.delta_excellent:
        return "Excellent"
    if loss <= config.delta_good:
        return "Good"
    if loss <= config.delta_inaccuracy:
        return "Inaccuracy"
    if loss <= config.delta_mistake:
        return "Mistake"
    return "Blunder"


# --- JSON Helper ---

def move_analysis_to_json(ma: MoveAnalysis) -> Dict[str, Any]:
    """Converts MoveAnalysis to a JSON-serializable dictionary."""
    return {
        "analysis_id": ma.analysis_id,
        "move_uci": ma.move_uci,
        "move_san": ma.move_san,
        "classification": ma.classification,
        "accuracy": ma.accuracy,
        "win_delta": round(ma.win_delta, 2),
        "cp_after": ma.cp_after,
        "is_book": ma.is_book_move,
        "is_forced": ma.is_forced,
        "is_check": ma.is_check,
        "comments": ma.comments,
        # Frontend Helpers
        "frontend_icon": _get_icon(ma.classification),
        "frontend_color": _get_color(ma.classification)
    }

def _get_icon(cls: str) -> str:
    cls = cls.lower()
    if cls in ['brilliant', 'great']: return 'exclamation'
    if cls == 'blunder': return 'skull'
    if cls == 'mistake': return 'question'
    if cls == 'inaccuracy': return 'question-mark-outline'
    if cls == 'book': return 'book'
    return 'check'

def _get_color(cls: str) -> str:
    cls = cls.lower()
    if cls == 'brilliant': return 'gold'
    if cls == 'great': return 'orange'
    if cls == 'blunder': return 'red'
    if cls == 'mistake': return 'orange-red'
    if cls == 'book': return 'blue'
    if cls == 'best': return 'green'
    if cls == 'excellent': return 'light-green'
    return 'grey'
