from __future__ import annotations

import os
from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("BOMBAVTEST_TEST_URL", "http://127.0.0.1:18000")


def login(page: Page, username: str, password: str):
    page.goto(f"{BASE_URL}/login")
    page.locator("#loginUsername").fill(username)
    page.locator("#loginPassword").fill(password)
    expect(page.locator("#loginSubmit")).to_be_enabled()
    page.locator("#loginSubmit").click()
    expect(page.locator("#homeView")).to_be_visible()


def test_login_and_logout_from_browser(page: Page):
    login(page, "test-admin", "TestAdmin123")
    expect(page.locator("#adminNavBtn")).to_be_visible()

    page.locator("#logoutBtn").click()
    expect(page.locator("#loginView")).to_be_visible()
    expect(page).to_have_url(f"{BASE_URL}/login")


def test_practice_answer_and_statistics_flow(
    page: Page, live_admin, live_topic_factory, live_question_factory, live_user_factory
):
    admin_client, headers = live_admin
    topic = live_topic_factory(admin_client, headers)
    question = live_question_factory(admin_client, headers, topic_id=topic["id"])
    user = live_user_factory(admin_client, headers, topic_ids=[topic["id"]])

    login(page, user["username"], user["password"])
    page.locator(f'[data-topic-play="{topic["id"]}"]').click()
    expect(page.locator("#questionTitle")).to_have_text(question["text"])

    page.locator(f'[data-option-id="{question["correct_id"]}"]').click()
    expect(page.locator("#questionFeedback")).to_contain_text("Respuesta correcta")
    expect(page.locator("#nextQuestionBtn")).to_be_enabled()

    page.locator("#exitQuestionBtn").click()
    expect(page.locator("#homeView")).to_be_visible()
    page.locator('[data-nav="stats"]').first.click()
    expect(page.locator("#statsView")).to_be_visible()
    expect(page.locator("#statsSummary")).to_contain_text("Preguntas respondidas")
    expect(page.locator("#statsSummary")).to_contain_text("1")
    expect(page.locator("#statsSummary")).to_contain_text("100")


def test_simulation_can_be_completed_and_reviewed(
    page: Page, live_admin, live_topic_factory, live_question_factory, live_user_factory
):
    admin_client, headers = live_admin
    topic = live_topic_factory(admin_client, headers)
    question = live_question_factory(admin_client, headers, topic_id=topic["id"])
    user = live_user_factory(admin_client, headers, topic_ids=[topic["id"]])

    login(page, user["username"], user["password"])
    page.locator(f'[data-topic-exam="{topic["id"]}"]').click()
    expect(page.locator("#examIntroModal")).to_be_visible()
    page.locator("#examQuestionCount").fill("1")
    page.locator("#confirmExamBtn").click()

    expect(page.locator("#questionTitle")).to_have_text(question["text"])
    page.locator(f'[data-option-id="{question["correct_id"]}"]').click()
    page.locator("#nextQuestionBtn").click()

    expect(page.locator("#reviewView")).to_be_visible()
    expect(page.locator("#reviewTitle")).to_have_text("Simulacro finalizado")
    expect(page.locator("#reviewSummary")).to_contain_text("100 %")
    expect(page.locator("#reviewSummary")).to_contain_text("Correctas")
