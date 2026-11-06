# Web app — Person 2

Interactive board, chat panel, position setup, PGN upload and game viewer, and arrows or
highlights from coach answers.

- Talks to `services/coach` for explanations and to the chess API for board state.
- May use chess.js for instant drag feedback only; the chess service decides legality.
- Displays and navigates the move tree returned by `/v1/game`; never parses PGN itself.
- In development, point the chess API URL at the mock (`http://localhost:8064`); it
  allows browser requests from any origin.
