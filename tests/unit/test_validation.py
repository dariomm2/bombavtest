from __future__ import annotations

import re

import pytest

from backend import admin


def test_username_normalization_is_predictable():
    assert admin.username_base_from_name("Álvaro Pérez") == "alvaro.perez"
    assert admin.username_base_from_name("  María-José  López  ") == "maria.jose.lopez"
    assert re.fullmatch(r"[A-Za-z0-9._-]{3,50}", admin.username_base_from_name("李"))


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  12.3  ", "12.3"),
        ("TEST-A", "TEST-A"),
        (123, "123"),
    ],
)
def test_topic_number_cleaning(raw, expected):
    assert admin.clean_topic_number(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "x" * 33, "1\n2"])
def test_topic_number_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        admin.clean_topic_number(raw)


def test_attachment_name_strips_path_and_control_characters():
    assert admin.clean_attachment_name("../../manual.pdf") == "manual.pdf"
    assert admin.clean_attachment_name("informe\x00final.pdf") == "informefinal.pdf"


@pytest.mark.parametrize("value", ["ab", "ab c", "ábc", "a" * 51])
def test_username_validator_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        admin.clean_username(value)


def test_password_validator_accepts_minimum_valid_password():
    password_hash = admin.new_password_hash("Clave123")
    assert password_hash.startswith("$argon2id$")


def test_attachment_name_strips_windows_paths_too():
    assert admin.clean_attachment_name(r"C:\\fakepath\\manual.pdf") == "manual.pdf"
    assert admin.clean_attachment_name(r"..\\..\\manual.pdf") == "manual.pdf"
