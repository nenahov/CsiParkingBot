"""Небольшие фабрики native rich-блоков для пользовательских экранов."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aiogram.types import (
    DisabledButton,
    InputRichBlockButtons,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichMessageButton,
    RichTextButton,
    RichTextUnion,
)


def cell(
        text: RichTextUnion,
        *,
        header: bool = False,
        align: str = "left",
) -> RichBlockTableCell:
    return RichBlockTableCell(
        text=text,
        align=align,
        valign="middle",
        is_header=True if header else None,
    )


def button(
        text: str,
        *,
        callback_data: str | None = None,
        style: str = "link",
        disabled: bool = False,
) -> RichTextButton:
    return RichTextButton(
        button=RichMessageButton(
            text=text,
            callback_data=callback_data,
            style=style,
            disabled=DisabledButton() if disabled else None,
        )
    )


def button_block(buttons: Iterable[RichMessageButton]) -> InputRichBlockButtons:
    return InputRichBlockButtons(buttons=list(buttons), align="center")


def heading(text: str, *, size: int = 2) -> InputRichBlockSectionHeading:
    return InputRichBlockSectionHeading(text=text, size=size)


def paragraph(text: RichTextUnion) -> InputRichBlockParagraph:
    return InputRichBlockParagraph(text=text)


def table(
        rows: list[list[RichBlockTableCell]],
        *,
        caption: RichTextUnion | None = None,
        compact: bool = True,
) -> InputRichBlockTable:
    return InputRichBlockTable(
        cells=rows,
        is_bordered=True,
        is_striped=True,
        is_compact=compact,
        caption=caption,
    )


def message(
        blocks: list[Any],
        *,
        fallback_text: str | None = None,
) -> tuple[InputRichMessage, str]:
    """Собрать rich-сообщение и его plain-text fallback."""

    return InputRichMessage(blocks=blocks), fallback_text or ""
