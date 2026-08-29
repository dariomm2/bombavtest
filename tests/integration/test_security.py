from __future__ import annotations



def test_sensitive_mutations_require_csrf(admin):
    client, _ = admin
    cases = [
        ("post", "/api/logout", {"json": {}}),
        ("post", "/api/answers", {"json": {}}),
        ("post", "/api/simulations", {"json": {}}),
        ("post", "/api/simulations/finish", {"json": {}}),
        ("post", "/api/admin/topics", {"json": {}}),
        ("put", "/api/admin/topics/1", {"json": {}}),
        ("delete", "/api/admin/topics/1", {}),
        (
            "post",
            "/api/admin/topic-attachment-drafts",
            {"files": {"file": ("csrf.txt", b"x", "text/plain")}},
        ),
        ("delete", "/api/admin/topic-attachment-drafts/1", {}),
        (
            "post",
            "/api/admin/topics/1/attachments",
            {"files": [("files", ("csrf.txt", b"x", "text/plain"))]},
        ),
        ("delete", "/api/admin/topics/1/attachments/1", {}),
        ("post", "/api/admin/questions", {"json": {}}),
        ("put", "/api/admin/questions/1", {"json": {}}),
        ("delete", "/api/admin/questions/1", {}),
        ("post", "/api/admin/users", {"json": {}}),
        ("put", "/api/admin/users/1", {"json": {}}),
        ("post", "/api/admin/users/1/deactivate", {"json": {}}),
        ("delete", "/api/admin/users/1", {}),
        ("post", "/api/admin/users/1/activate", {"json": {}}),
    ]

    for method, path, kwargs in cases:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 403, f"{method.upper()} {path}: {response.text}"
        assert response.json().get("code") == "CSRF", f"{method.upper()} {path}: {response.text}"


def test_admin_surface_rejects_regular_users(admin, user_factory, login_user):
    admin_client, headers = admin
    user_factory(admin_client, headers, username="regular.user")
    client, user_headers = login_user(admin_client.app, "regular.user")

    cases = [
        ("get", "/api/admin/topics", {}),
        ("get", "/api/admin/questions", {}),
        ("get", "/api/admin/users", {}),
        ("get", "/api/admin/users/username-suggestion?display_name=Test", {}),
        ("post", "/api/admin/topics", {"headers": user_headers, "json": {}}),
        ("post", "/api/admin/questions", {"headers": user_headers, "json": {}}),
        ("post", "/api/admin/users", {"headers": user_headers, "json": {}}),
        (
            "post",
            "/api/admin/topic-attachment-drafts",
            {
                "headers": user_headers,
                "files": {"file": ("forbidden.txt", b"x", "text/plain")},
            },
        ),
    ]

    for method, path, kwargs in cases:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 403, f"{method.upper()} {path}: {response.text}"
        assert response.json().get("code") == "FORBIDDEN", f"{method.upper()} {path}: {response.text}"
