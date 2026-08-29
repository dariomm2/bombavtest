from __future__ import annotations

import os
import uuid

from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("BOMBAVTEST_TEST_URL", "http://127.0.0.1:18000")


def login_admin(page: Page):
    page.goto(f"{BASE_URL}/login")
    page.locator("#loginUsername").fill("test-admin")
    page.locator("#loginPassword").fill("TestAdmin123")
    page.locator("#loginSubmit").click()
    expect(page.locator("#homeView")).to_be_visible()
    page.locator("#adminNavBtn").click()
    expect(page.locator("#adminView")).to_be_visible()


def test_admin_question_crud_from_browser(page: Page):
    marker = uuid.uuid4().hex[:10]
    original = f"Pregunta navegador {marker}"
    edited = f"Pregunta editada {marker}"

    login_admin(page)
    page.locator('[data-admin-tab="questions"]').click()
    expect(page.locator("#adminCreateBtn")).to_have_text("Nueva pregunta")
    page.locator("#adminCreateBtn").click()

    page.locator("#adminQuestionText").fill(original)
    options = page.locator("#adminOptionsEditor .admin-option-text")
    options.nth(0).fill(f"Correcta {marker}")
    options.nth(1).fill(f"Incorrecta {marker}")
    expect(page.locator("#adminSaveBtn")).to_be_enabled()
    page.locator("#adminSaveBtn").click()

    row = page.locator("#adminList tbody tr", has_text=original)
    expect(row).to_have_count(1)
    row.locator('[data-admin-edit="questions"]').click()
    page.locator("#adminQuestionText").fill(edited)
    page.locator("#adminSaveBtn").click()

    edited_row = page.locator("#adminList tbody tr", has_text=edited)
    expect(edited_row).to_have_count(1)
    edited_row.locator('[data-admin-delete="questions"]').click()
    expect(page.locator("#adminDeleteModal")).to_be_visible()
    page.locator("#adminConfirmDeleteBtn").click()
    expect(page.locator("#adminList tbody tr", has_text=edited)).to_have_count(0)


def test_admin_can_create_and_deactivate_user_from_browser(page: Page):
    marker = uuid.uuid4().hex[:10]
    display_name = f"Usuario navegador {marker}"
    username = f"browser.{marker}"

    login_admin(page)
    page.locator('[data-admin-tab="users"]').click()
    expect(page.locator("#adminCreateBtn")).to_have_text("Nuevo usuario")
    page.locator("#adminCreateBtn").click()

    page.locator("#adminUserDisplayName").fill(display_name)
    page.locator("#adminUsername").fill(username)
    page.locator("#adminUserPassword").fill("Clave123")
    expect(page.locator("#adminUsernameStatus")).to_have_text("Disponible")
    expect(page.locator("#adminSaveBtn")).to_be_enabled()
    page.locator("#adminSaveBtn").click()

    row = page.locator("#adminList tbody tr", has_text=username)
    expect(row).to_have_count(1)
    row.locator("[data-admin-deactivate-user]").click()
    expect(page.locator("#adminDeleteModal")).to_be_visible()
    page.locator("#adminConfirmDeleteBtn").click()

    row = page.locator("#adminList tbody tr", has_text=username)
    expect(row).to_contain_text("De baja")
