"""Draw a puzzle position as a PNG, like a screenshot a player would upload: the board seen from
the solver's side, file/rank labels, and the opponent's last move highlighted."""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import chess
from PIL import Image, ImageDraw, ImageFont

SQ = 80
MARGIN = 28
LIGHT, DARK = (240, 217, 181), (181, 136, 99)
LIGHT_HI, DARK_HI = (247, 236, 116), (218, 195, 74)
FONTS = ["/System/Library/Fonts/Apple Symbols.ttf", "/Library/Fonts/Arial Unicode.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
SOLID = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}
OUTLINE = {"k": "♔", "q": "♕", "r": "♖", "b": "♗", "n": "♘", "p": "♙"}


@lru_cache(maxsize=4)
def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("no font with chess symbols found")


def render(fen: str, white_bottom: bool, last_move: str | None = None) -> bytes:
    board = chess.Board(fen)
    hi = set()
    if last_move:
        m = chess.Move.from_uci(last_move)
        hi = {m.from_square, m.to_square}
    size = 8 * SQ + 2 * MARGIN
    img = Image.new("RGB", (size, size), (48, 46, 43))
    d = ImageDraw.Draw(img)
    piece_font, label_font = _font(int(SQ * 0.82)), _font(17)

    for row in range(8):
        for col in range(8):
            file, rank = (col, 7 - row) if white_bottom else (7 - col, row)
            sq = chess.square(file, rank)
            light = (file + rank) % 2 == 1
            color = (LIGHT_HI if light else DARK_HI) if sq in hi else (LIGHT if light else DARK)
            x, y = MARGIN + col * SQ, MARGIN + row * SQ
            d.rectangle([x, y, x + SQ, y + SQ], fill=color)
            piece = board.piece_at(sq)
            if piece:
                sym = piece.symbol().lower()
                cx, cy = x + SQ / 2, y + SQ / 2 + 2
                if piece.color == chess.WHITE:
                    d.text((cx, cy), SOLID[sym], font=piece_font, fill=(255, 255, 255), anchor="mm")
                    d.text((cx, cy), OUTLINE[sym], font=piece_font, fill=(0, 0, 0), anchor="mm")
                else:
                    d.text((cx, cy), SOLID[sym], font=piece_font, fill=(0, 0, 0), anchor="mm")

    for i in range(8):
        f = "abcdefgh"[i if white_bottom else 7 - i]
        r = str(8 - i if white_bottom else i + 1)
        d.text((MARGIN + i * SQ + SQ / 2, size - MARGIN / 2), f, font=label_font, fill=(220, 220, 220), anchor="mm")
        d.text((MARGIN / 2, MARGIN + i * SQ + SQ / 2), r, font=label_font, fill=(220, 220, 220), anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
