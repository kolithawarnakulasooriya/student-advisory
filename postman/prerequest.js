// Session IDs stay in Postman's cookie jar, never in collection/environment variables.
const method = pm.request.method;
if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    pm.request.headers.upsert({key: "Origin", value: pm.variables.get("web_origin")});
    if (!pm.request.url.toString().includes("/auth/")) {
        const override = pm.variables.get("idempotency_key");
        pm.variables.set("operation_key", override || pm.variables.replaceIn("{{$guid}}"));
    }
    // Fetch on every mutation: sign-in, verification and MFA rotate the session.
    pm.sendRequest({
        url: pm.variables.get("base_url").replace(/\/$/, "") + "/api/v1/auth/csrf",
        method: "GET",
        header: {Accept: "application/json"}
    }, (error, response) => {
        if (error || response.code !== 200) {
            pm.execution.skipRequest();
            throw new Error("CSRF setup failed. Check the local API and cookie jar.");
        }
        const csrf = response.json().csrf_token;
        pm.variables.set("csrf_token", csrf);
        // Synthetic verification can obtain a fresh challenge without persisting it.
        if (pm.request.url.toString().endsWith("/auth/verify") && !pm.variables.get("verification_challenge")) {
            pm.sendRequest({
                url: pm.variables.get("base_url").replace(/\/$/, "") + "/api/v1/auth/simulator/challenge",
                method: "POST",
                header: {Origin: pm.variables.get("web_origin"), "X-CSRF-Token": csrf}
            }, (challengeError, challengeResponse) => {
                if (challengeError || challengeResponse.code !== 200) {
                    pm.execution.skipRequest();
                    throw new Error("Challenge unavailable. Register or sign in as an unverified identity first.");
                }
                pm.variables.set("verification_challenge", challengeResponse.json().simulator_challenge);
            });
        }
    });
}
