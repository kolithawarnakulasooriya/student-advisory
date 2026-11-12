pm.test("Protected responses are not cached", () => {
    pm.expect(pm.response.headers.get("Cache-Control")).to.equal("no-store");
});
pm.test("Server provides a correlation ID", () => {
    pm.expect(pm.response.headers.get("X-Correlation-Id")).to.be.a("string").and.not.empty;
});
// Request-specific tests assert happy-path or intentionally denied status codes.
// Do not log cookies, challenges, invitation tokens, request bodies or response bodies.
