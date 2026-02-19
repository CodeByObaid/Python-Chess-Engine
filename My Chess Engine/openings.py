import requests
import chess

def detect_opening(board):
    """
    Detects the opening based on the current board position (EPD).
    Returns (eco, name) or None if not found.
    """
    epd = board.epd(hmvc=board.halfmove_clock, fmvc=board.fullmove_number)
    # simpler epd for opening generic lookup (ignoring clocks)
    key = " ".join(epd.split(" ")[:4])
    return ECO_DB.get(key)

# Common Openings Database (EPD/FEN fragment -> (ECO, Name))
ECO_DB = {
    # Initial Position
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -": ("A00", "Start Position"),

    # A00 - Irregular Openings
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -": ("B00", "King's Pawn Opening"),
    "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq -": ("D00", "Queen's Pawn Opening"),
    "rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R b KQkq -": ("A04", "Réti Opening"),
    "rnbqkbnr/pppppppp/8/8/2P5/8/PP1PPPPP/RNBQKBNR b KQkq -": ("A10", "English Opening"),

    # B00-B99 - Semi-Open Games
    "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": ("C00", "French Defence"),
    "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": ("B10", "Caro-Kann Defence"),
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": ("B20", "Sicilian Defence"),
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": ("C20", "King's Pawn Game"), # e4 e5
    
    # Sicilian Variations
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq -": ("B27", "Sicilian Defence: Knight Variation"),
    "rnbqkb1r/pp1ppppp/5n2/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -": ("B29", "Sicilian Defence: Nimzowitsch-Rubinstein"),
    
    # C00-C99 - Open Games (1.e4 e5)
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq -": ("C40", "King's Knight Opening"),
    "rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -": ("C42", "Petrov's Defence"),
    "rnbqkb1r/pppp1ppp/8/4p3/4P3/2n2N2/PPPP1PPP/RNBQKB1R w KQkq -": ("C42", "Petrov's Defence (Stafford Gambit)"), # Joke/Trap line often played
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -": ("C44", "King's Knight Opening"),
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/2N2N2/PPPP1PPP/R1BQKB1R b KQkq -": ("C46", "Three Knights Game"),
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/2N2N2/PPPP1PPP/R1BQKB1R w KQkq -": ("C47", "Four Knights Game"),
    "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq -": ("C60", "Ruy Lopez"),
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq -": ("C50", "Italian Game"),
    
    # D00-D99 - Closed Games (1.d4 d5)
    "rnbqkbnr/ppp1pppp/8/3p4/3P4/8/PPP1PPPP/RNBQKBNR w KQkq -": ("D00", "Queen's Pawn Game"),
    "rnbqkbnr/ppp1pppp/8/3p4/2PP4/8/PP2PPPP/RNBQKBNR b KQkq -": ("D06", "Queen's Gambit"),
    "rnbqkbnr/ppp1pppp/8/3p4/2PP4/8/PP2PPPP/RNBQKBNR w KQkq -": ("D06", "Queen's Gambit"),
    
    # Indian Defences (1.d4 Nf6)
    "rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq -": ("A45", "Indian Game"),
    "rnbqkb1r/pppppppp/5n2/8/2PP4/8/PP2PPPP/RNBQKBNR b KQkq -": ("E00", "Indian Game (Normal)"),
    "rnbqkb1r/pppp1ppp/4pn2/8/2PP4/8/PP2PPPP/RNBQKBNR w KQkq -": ("E11", "Bogo-Indian Defence"),
    "rnbqkb1r/pp1ppppp/2p2n2/8/2PP4/8/PP2PPPP/RNBQKBNR w KQkq -": ("D10", "Slav Defence"),
    
    # Specific Famous Lines (for quick recognition)
    "rnbqkbnr/ppp2ppp/4p3/3p4/3PP3/8/PPP2PPP/RNBQKBNR w KQkq -": ("C01", "French Defence: Exchange"),
    "rnbqkbnr/ppp2ppp/4p3/3p4/3PP3/2N5/PPP2PPP/R1BQKBNR b KQkq -": ("C10", "French Defence: Paulsen"),
    
    # ... (Keep your existing entries) ...

    # --- Flank Openings (White) ---
    "rnbqkbnr/pppppppp/8/8/5P2/8/PPPPP1PP/RNBQKBNR b KQkq -": ("A02", "Bird's Opening"),
    "rnbqkbnr/pppppppp/8/8/8/1P6/P1PPPPPP/RNBQKBNR b KQkq -": ("A01", "Nimzo-Larsen Attack"),
    "rnbqkbnr/pppppppp/8/8/8/6P1/PPPPPPPP/RNBQKBNR b KQkq -": ("A00", "Hungarian Opening"), # 1. g3

    # --- Semi-Open Games (1. e4, black plays other than e5) ---
    "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": ("B01", "Scandinavian Defence"),
    "rnbqkb1r/pppppppp/5n2/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": ("B02", "Alekhine's Defence"),
    "rnbqkbnr/pppp1ppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": ("B00", "Nimzowitsch Defence"), # 1... Nc6
    "rnbqkbnr/ppp1pppp/3p4/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": ("B07", "Pirc Defence"),
    "rnbqkbnr/pppppp1p/6p1/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": ("B06", "Modern Defence"),

    # --- Sicilian Defence (1. e4 c5) Extensions ---
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/2N5/PPPP1PPP/R1BQKBNR b KQkq -": ("B23", "Sicilian Defence: Closed"),
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/2P5/PP1P1PPP/RNBQKBNR b KQkq -": ("B22", "Sicilian Defence: Alapin Variation"),
    "rnbqkbnr/pp1ppppp/8/2p5/3PP3/8/PPP2PPP/RNBQKBNR b KQkq -": ("B21", "Sicilian Defence: Smith-Morra Gambit"),
    
    # Common Sicilian Tabiyas (Mid-opening)
    # Dragon / Najdorf Base (1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3)
    "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R b KQkq -": ("B50", "Sicilian: Classical Setup"), 
    # Najdorf (5... a6)
    "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq -": ("B90", "Sicilian: Najdorf Variation"),
    # Dragon (5... g6)
    "rnbqkb1r/pp2pp1p/3p1n2/6p1/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq -": ("B70", "Sicilian: Dragon Variation"),

    # --- Open Games (1. e4 e5) Extensions ---
    "rnbqkbnr/pppp1ppp/8/4p3/4PP2/8/PPPP2PP/RNBQKBNR b KQkq -": ("C30", "King's Gambit"),
    "rnbqkbnr/ppp2ppp/3p4/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -": ("C41", "Philidor Defence"),
    "r1bqkbnr/pppp1ppp/2n5/4p3/3PP3/5N2/PPP2PPP/RNBQKB1R b KQkq -": ("C45", "Scotch Game"),
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/2N5/PPPP1PPP/R1BQKBNR b KQkq -": ("C25", "Vienna Game"),
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/8/PPPP1PPP/RNBQK1NR b KQkq -": ("C23", "Bishop's Opening"),
    # Fried Liver Attack Setup
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq -": ("C55", "Two Knights Defence"),

    # --- Queen's Pawn (1. d4) Extensions ---
    "rnbqkbnr/ppp1pppp/8/3p4/3P1B2/8/PPP1PPPP/RN1QKBNR b KQkq -": ("D02", "London System"),
    "rnbqkbnr/ppppp1pp/8/5p2/3P4/8/PPP1PPPP/RNBQKBNR w KQkq -": ("A80", "Dutch Defence"),
    "rnbqkbnr/ppp1pppp/8/3p4/2PP4/2N5/PP2PPPP/R1BQKBNR b KQkq -": ("D06", "Queen's Gambit: Veresov"),
    
    # 1. d4 Nf6 responses
    "rnbqkb1r/pppppppp/5n2/8/3P4/2N5/PPP1PPPP/R1BQKBNR b KQkq -": ("D00", "Richter-Veresov Attack"),
    "rnbqkb1r/pppppppp/5n2/8/3P4/5N2/PPP1PPPP/RNBQKB1R b KQkq -": ("A46", "Torre Attack / Other d4 systems"),
    
    # Benoni Systems (1. d4 c5)
    "rnbqkbnr/pp1ppppp/8/2p5/3P4/8/PPP1PPPP/RNBQKBNR w KQkq -": ("A43", "Old Benoni"),
    "rnbqkb1r/pp1ppppp/5n2/2p5/3P4/5N2/PPP1PPPP/RNBQKB1R w KQkq -": ("A43", "Benoni Defence"),

    # --- Indian Defences (Deepening) ---
    # King's Indian (1. d4 Nf6 2. c4 g6)
    "rnbqkb1r/pppppp1p/5np1/8/2PP4/8/PP2PPPP/RNBQKBNR w KQkq -": ("E60", "King's Indian / Grunfeld Setup"),
    # Grunfeld (1. d4 Nf6 2. c4 g6 3. Nc3 d5)
    "rnbqkb1r/ppp1pp1p/5np1/3p4/2PP4/2N5/PP2PPPP/R1BQKBNR w KQkq -": ("D80", "Grünfeld Defence"),
    # Nimzo-Indian (1. d4 Nf6 2. c4 e6 3. Nc3 Bb4)
    "rnbqk2r/pppp1ppp/4pn2/8/1bPP4/2N5/PP2PPPP/R1BQKBNR w KQkq -": ("E20", "Nimzo-Indian Defence"),
    # Queen's Indian (1. d4 Nf6 2. c4 e6 3. Nf3 b6)
    "rnbqkb1r/p1pppppp/1p3n2/8/2PP4/5N2/PP2PPPP/RNBQKB1R w KQkq -": ("E12", "Queen's Indian Defence"),
    # Catalan (1. d4 Nf6 2. c4 e6 3. g3)
    "rnbqkb1r/pppp1ppp/4pn2/8/2PP4/6P1/PP2PP1P/RNBQKBNR b KQkq -": ("E00", "Catalan Opening"),

    # --- English Opening Variations ---
    # Symmetrical (1. c4 c5)
    "rnbqkbnr/pp1ppppp/8/2p5/2P5/8/PP1PPPPP/RNBQKBNR w KQkq -": ("A30", "English: Symmetrical"),
    # Reversed Sicilian (1. c4 e5)
    "rnbqkbnr/pppp1ppp/8/4p3/2P5/8/PP1PPPPP/RNBQKBNR w KQkq -": ("A20", "English: King's English"),
}
