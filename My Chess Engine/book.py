import requests
import chess

class BookManager:
    def __init__(self):
        self.base_url = "https://explorer.lichess.ovh/masters"
        self._cache = {}
        # Limit to first 20 moves for book lookups to save resources and API calls
        self.move_limit = 20

    def get_book_moves(self, fen):
        """
        Fetches book moves for a given FEN from Lichess Masters DB.
        Returns a set of UCI moves that are considered 'Book'.
        """
        # Canonicalize FEN (remove move numbers/clocks for caching)
        board = chess.Board(fen)
        key = board.epd() # EPD is good for caching positions
        
        if key in self._cache:
            return self._cache[key]

        try:
            # Lichess API parameters
            params = {'fen': fen, 'moves': 10} # Get top 10 moves
            resp = requests.get(self.base_url, params=params, timeout=2)
            
            if resp.status_code == 200:
                data = resp.json()
                moves = data.get('moves', [])
                # A move is "Book" if it has been played by masters
                book_moves = set(m['uci'] for m in moves)
                self._cache[key] = book_moves
                return book_moves
            else:
                print(f"Book API Error: {resp.status_code}")
                return set()
        except Exception as e:
            print(f"Book API Exception: {e}")
            return set()

    def is_book_move(self, board, move_uci):
        """
        Checks if a move is a book move in the current position.
        """
        if board.fullmove_number > self.move_limit:
            return False

        fen = board.fen()
        book_moves = self.get_book_moves(fen)
        return move_uci in book_moves
