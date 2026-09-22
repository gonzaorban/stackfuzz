"""Tests for signature-based stack detection."""

import httpx
import pytest

from stackfuzz.detector import PROBE_PATHS, Probe, Tech, detect, fetch_target


# --- detect(): rule coverage --------------------------------------------


def test_empty_probe_detects_nothing():
    assert detect(Probe()) == set()


def test_django_via_cookies():
    assert detect(Probe(cookies={"csrftoken": "x"})) == {Tech.DJANGO}
    assert detect(Probe(cookies={"sessionid": "x"})) == {Tech.DJANGO}


def test_django_via_admin_probe_and_powered_by():
    probe = Probe(
        headers={"x-powered-by": "Django"},
        probe_paths={"/admin/": 302},
    )
    assert Tech.DJANGO in detect(probe)


def test_admin_probe_alone_is_not_django():
    # /admin/ is common to many stacks, so it must not trigger Django by itself.
    assert detect(Probe(probe_paths={"/admin/": 302})) == set()


def test_nextjs_via_powered_by():
    assert detect(Probe(headers={"x-powered-by": "Next.js"})) == {Tech.NEXTJS}


def test_nextjs_via_custom_header():
    assert detect(Probe(headers={"x-nextjs-cache": "HIT"})) == {Tech.NEXTJS}


def test_nextjs_via_probe_path():
    assert detect(Probe(probe_paths={"/_next/": 200})) == {Tech.NEXTJS}


def test_express_via_powered_by():
    assert detect(Probe(headers={"x-powered-by": "Express"})) == {Tech.EXPRESS}


def test_flask_via_werkzeug_server():
    assert detect(Probe(headers={"server": "Werkzeug/3.0.1 Python/3.13"})) == {
        Tech.FLASK
    }


def test_flask_session_cookie_but_not_when_django():
    assert detect(Probe(cookies={"session": "x"})) == {Tech.FLASK}
    # A Django session cookie present -> the bare 'session' rule must not fire.
    django = Probe(cookies={"session": "x", "csrftoken": "y"})
    assert detect(django) == {Tech.DJANGO}


def test_laravel_via_cookies():
    assert detect(Probe(cookies={"laravel_session": "x"})) == {Tech.LARAVEL}
    assert detect(Probe(cookies={"xsrf-token": "x"})) == {Tech.LARAVEL}


def test_multiple_techs_detected_together():
    probe = Probe(
        headers={"x-powered-by": "Next.js"},
        cookies={"csrftoken": "x"},
    )
    assert detect(probe) == {Tech.NEXTJS, Tech.DJANGO}


def test_detection_is_case_insensitive():
    assert detect(Probe(headers={"x-powered-by": "EXPRESS"})) == {Tech.EXPRESS}


# --- fetch_target(): recon over a mocked transport ----------------------


def test_fetch_target_collects_headers_cookies_and_probes():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in ("", "/"):
            return httpx.Response(
                200,
                headers={"x-powered-by": "Next.js", "set-cookie": "sid=abc"},
                text="ok",
            )
        # Probe paths: pretend /_next/ exists, others 404.
        if request.url.path == "/_next/":
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    # fetch_target builds its own client, so patch httpx.Client to use the mock.
    original = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    httpx.Client = client_factory
    try:
        probe = fetch_target("https://example.com")
    finally:
        httpx.Client = original

    assert probe.status == 200
    assert probe.header("x-powered-by") == "Next.js"
    assert probe.has_cookie("sid")
    assert probe.probe_paths["/_next/"] == 200
    assert probe.probe_paths["/admin/"] == 404
    assert set(probe.probe_paths) == set(PROBE_PATHS)
    # End to end: this probe should detect Next.js.
    assert Tech.NEXTJS in detect(probe)


def test_fetch_target_raises_on_base_request_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    original = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    httpx.Client = client_factory
    try:
        with pytest.raises(httpx.HTTPError):
            fetch_target("https://example.com")
    finally:
        httpx.Client = original
