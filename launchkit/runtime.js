(function () {
  var cfg = window.LAUNCH_CONFIG || {};
  var api = function (fn, payload) {
    return fetch(cfg.functionsUrl + "/" + fn, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: cfg.anonKey || "" },
      body: JSON.stringify(payload),
    }).then(function (res) {
      return res.json().then(function (body) {
        if (!res.ok) throw new Error(body.error || "Something went wrong.");
        return body;
      });
    });
  };

  var toast = function (message, isError) {
    var el = document.getElementById("launch-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "launch-toast";
      el.setAttribute("role", "status");
      el.style.cssText =
        "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:9999;" +
        "max-width:90vw;padding:12px 20px;border-radius:10px;font:500 15px system-ui;" +
        "box-shadow:0 10px 30px rgba(0,0,0,.25);color:#fff";
      document.body.appendChild(el);
    }
    el.style.background = isError ? "#b91c1c" : "#0f172a";
    el.textContent = message;
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.remove(); }, 6000);
  };

  var utm = {};
  var params = new URLSearchParams(location.search);
  params.forEach(function (v, k) { if (k.indexOf("utm_") === 0) utm[k] = v; });
  var selectedPlan = null;

  var joinWaitlist = function (email, plan) {
    return api("waitlist-signup", {
      email: email,
      plan_interest: plan || selectedPlan,
      source: document.referrer || "direct",
      utm: utm,
    }).then(function (body) { toast(body.message); });
  };

  var waitlistForm = document.getElementById("waitlist-form");
  if (waitlistForm) {
    var honeypot = document.createElement("input");
    honeypot.name = "website";
    honeypot.tabIndex = -1;
    honeypot.autocomplete = "off";
    honeypot.setAttribute("aria-hidden", "true");
    honeypot.style.cssText = "position:absolute;left:-9999px;width:1px;height:1px";
    waitlistForm.appendChild(honeypot);

    waitlistForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (honeypot.value) return;
      var email = waitlistForm.elements.email.value;
      var button = waitlistForm.querySelector("[type=submit]");
      if (button) button.disabled = true;
      (selectedPlan ? checkout(email, selectedPlan) : joinWaitlist(email))
        .then(function () { waitlistForm.reset(); })
        .catch(function (err) { toast(err.message, true); })
        .finally(function () { if (button) button.disabled = false; });
    });
  }

  // Pricing buttons: the server decides. Stripe Checkout once PAYMENTS_ENABLED is
  // on; until then the signup is stored with the plan as a pricing signal.
  var checkout = function (email, plan) {
    return api("create-checkout", { email: email, plan: cfg.planPrefix + plan + "_monthly" })
      .then(function (body) {
        if (body.url) location.href = body.url;
        else return joinWaitlist(email, plan);
      });
  };

  document.querySelectorAll("[data-plan]").forEach(function (button) {
    button.addEventListener("click", function (e) {
      e.preventDefault();
      selectedPlan = button.getAttribute("data-plan");
      if (!waitlistForm) return;
      var email = waitlistForm.elements.email.value;
      if (email && waitlistForm.checkValidity()) {
        checkout(email, selectedPlan).catch(function (err) { toast(err.message, true); });
        return;
      }
      waitlistForm.scrollIntoView({ behavior: "smooth", block: "center" });
      waitlistForm.elements.email.focus();
      toast("Enter your email to reserve the " + button.getAttribute("data-plan") + " plan.");
    });
  });

  // "Manage subscription": emails a signed link to the Stripe customer portal.
  var footer = document.querySelector("footer") || document.body;
  var billing = document.createElement("form");
  billing.id = "billing-form";
  billing.style.cssText = "display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:16px auto;font:14px system-ui";
  billing.innerHTML =
    '<label for="billing-email" style="align-self:center;opacity:.75">Manage your subscription:</label>' +
    '<input id="billing-email" name="email" type="email" required placeholder="you@company.com" ' +
    'style="padding:6px 10px;border:1px solid #cbd5e1;border-radius:8px;color:#0f172a">' +
    '<button type="submit" style="padding:6px 12px;border-radius:8px;background:#0f172a;color:#fff">Email me a link</button>';
  footer.appendChild(billing);
  billing.addEventListener("submit", function (e) {
    e.preventDefault();
    api("billing-portal", { email: billing.elements.email.value })
      .then(function (body) { toast(body.message); billing.reset(); })
      .catch(function (err) { toast(err.message, true); });
  });

  // Day-2 validation: ?feedback=<token> from onboarding emails.
  var feedbackToken = params.get("feedback");
  if (feedbackToken) {
    var panel = document.createElement("form");
    panel.style.cssText =
      "position:fixed;inset:auto 16px 16px auto;z-index:9998;width:min(420px,calc(100vw - 32px));" +
      "background:#fff;color:#0f172a;padding:20px;border-radius:14px;box-shadow:0 20px 50px rgba(0,0,0,.3);font:15px system-ui";
    panel.innerHTML =
      '<label for="pain" style="display:block;font-weight:600;margin-bottom:8px">' +
      "What is the most frustrating part of this problem for you today?</label>" +
      '<textarea id="pain" name="pain" rows="4" required style="width:100%;border:1px solid #cbd5e1;border-radius:8px;padding:8px"></textarea>' +
      '<button type="submit" style="margin-top:10px;padding:8px 14px;border-radius:8px;background:#0f172a;color:#fff">Send</button>';
    document.body.appendChild(panel);
    panel.addEventListener("submit", function (e) {
      e.preventDefault();
      api("waitlist-action", { action: "feedback", token: feedbackToken, pain_point: panel.elements.pain.value })
        .then(function () { panel.remove(); toast("Thank you - this shapes what we build first."); })
        .catch(function (err) { toast(err.message, true); });
    });
  }

  var notices = {
    confirmed: "You're confirmed. Welcome aboard!",
    unsubscribed: "You've been unsubscribed.",
  };
  Object.keys(notices).forEach(function (k) { if (params.get(k)) toast(notices[k]); });
  if (params.get("checkout") === "success") toast("Payment received - check your inbox.");
  if (params.get("error")) toast("That link is invalid or has expired.", true);
})();
