"""Разбор логических выражений в AST.

Поддерживается школьная и «программистская» нотация одновременно:

===== ==========================================
НЕ    ¬A, !A, not A, НЕ A
И     A∧B, A&B, A·B, A*B, A/\\B, A and B, A И B
ИЛИ   A∨B, A|B, A+B, A\\/B, A or B, A ИЛИ B
XOR   A⊕B, A^B, A xor B, A искл B
→     A→B, A->B, A=>B, A implies B, A имп B
≡     A≡B, A↔B, A⇔B, A<=>B, A==B, A=B, A экв B
===== ==========================================

Важно: ``+`` трактуется как ИЛИ (школьная запись), поэтому арифметики здесь нет.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .ast import Bin, Node, Not, Var


class ParseError(ValueError):
    """Ошибка разбора: сообщение содержит позицию."""

    def __init__(self, message: str, text: str, pos: int) -> None:
        caret = " " * max(pos, 0) + "^"
        super().__init__(f"{message} (позиция {pos})\n{text}\n{caret}")
        self.text = text
        self.pos = pos


@dataclass(frozen=True)
class Token:
    kind: str  # VAR | NOT | AND | OR | XOR | IMPL | EQV | LPAREN | RPAREN
    value: str
    pos: int


# Порядок правил важен: составные операторы проверяются раньше односимвольных.
_RULES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("COMMENT", re.compile(r"#[^\n]*")),
    ("SKIP", re.compile(r"[ \t\r\n]+")),
    ("LPAREN", re.compile(r"\(")),
    ("RPAREN", re.compile(r"\)")),
    ("EQV", re.compile(r"<=>|==|≡|↔|⇔|=|(?i:equiv)\b|(?i:экв)\b")),
    ("IMPL", re.compile(r"->|=>|→|⇒|⟶|(?i:implies)\b|(?i:imp)\b|(?i:имп)\b")),
    ("XOR", re.compile(r"⊕|⇗|\^|(?i:xor)\b|(?i:искл)\b")),
    ("AND", re.compile(r"&&|/\\|∧|&|·|⋅|\*|(?i:and)\b|(?i:и)\b")),
    ("OR", re.compile(r"\|\||\\/|∨|\||\+|(?i:or)\b|(?i:или)\b")),
    ("NOT", re.compile(r"¬|!|~|(?i:not)\b|(?i:не)\b")),
    ("VAR", re.compile(r"[A-Za-z][A-Za-z0-9_]*")),
)


def tokenize(text: str) -> List[Token]:
    tokens: List[Token] = []
    pos = 0
    length = len(text)
    while pos < length:
        for kind, pattern in _RULES:
            match = pattern.match(text, pos)
            if match is None:
                continue
            lexeme = match.group(0)
            if kind not in ("SKIP", "COMMENT"):
                tokens.append(Token(kind, lexeme, pos))
            pos = match.end()
            break
        else:
            raise ParseError(f"недопустимый символ {text[pos]!r}", text, pos)
    return tokens


class _Parser:
    def __init__(self, text: str, tokens: List[Token]) -> None:
        self.text = text
        self.tokens = tokens
        self.i = 0

    # -- вспомогательное ---------------------------------------------------- #
    def peek(self) -> Optional[Token]:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def advance(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def fail(self, message: str) -> ParseError:
        tok = self.peek()
        pos = tok.pos if tok else len(self.text)
        return ParseError(message, self.text, pos)

    # -- грамматика --------------------------------------------------------- #
    def parse(self) -> Node:
        if not self.tokens:
            raise ParseError("пустое выражение", self.text, 0)
        node = self.parse_binary(1)
        tok = self.peek()
        if tok is not None:
            raise self.fail(f"лишний фрагмент {tok.value!r} после выражения")
        return node

    def parse_binary(self, min_prec: int) -> Node:
        left = self.parse_unary()
        from .ast import PRECEDENCE, RIGHT_ASSOC  # локально, чтобы избежать цикла

        while True:
            tok = self.peek()
            if tok is None or tok.kind not in PRECEDENCE:
                return left
            prec = PRECEDENCE[tok.kind]
            if prec < min_prec:
                return left
            self.advance()
            next_min = prec if tok.kind in RIGHT_ASSOC else prec + 1
            right = self.parse_binary(next_min)
            left = Bin(tok.kind, left, right)

    def parse_unary(self) -> Node:
        tok = self.peek()
        if tok is not None and tok.kind == "NOT":
            self.advance()
            return Not(self.parse_unary())
        return self.parse_atom()

    def parse_atom(self) -> Node:
        tok = self.peek()
        if tok is None:
            raise self.fail("неожиданный конец выражения")
        if tok.kind == "LPAREN":
            self.advance()
            node = self.parse_binary(1)
            closing = self.peek()
            if closing is None or closing.kind != "RPAREN":
                raise self.fail("не закрыта скобка")
            self.advance()
            return node
        if tok.kind == "VAR":
            self.advance()
            return Var(tok.value)
        raise self.fail(f"ожидалась переменная или '(', получено {tok.value!r}")


def parse(text: str) -> Node:
    """Разобрать выражение в AST. Бросает :class:`ParseError` на некорректном вводе."""
    return _Parser(text, tokenize(text)).parse()


def try_parse(text: str) -> Tuple[Optional[Node], Optional[str]]:
    """Безопасный разбор: ``(ast, None)`` либо ``(None, текст ошибки)``."""
    try:
        return parse(text), None
    except ParseError as exc:
        return None, str(exc)
