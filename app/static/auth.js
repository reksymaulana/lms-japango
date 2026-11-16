import { createAuthClient } from "@neon/auth";

const root = document.getElementById("auth-root");

if (root) {
  const status = document.getElementById("auth-status");
  const forms = document.getElementById("auth-forms");
  const signupForm = document.getElementById("signup-form");
  const signinForm = document.getElementById("signin-form");
  const sessionPanel = document.getElementById("auth-session");
  const userEmail = document.getElementById("auth-user-email");
  const userRole = document.getElementById("auth-user-role");
  const userIdLabel = document.getElementById("auth-user-id-label");
  const userId = document.getElementById("auth-user-id");
  const dashboardLink = document.getElementById("auth-dashboard-link");
  const signoutButton = document.getElementById("signout-button");
  const signupTab = document.getElementById("show-signup");
  const signinTab = document.getElementById("show-signin");

  function showStatus(message, isError = false) {
    status.textContent = message;
    status.hidden = !message;
    status.classList.toggle("text-rose-700", isError);
    status.classList.toggle("bg-rose-50", isError);
    status.classList.toggle("text-slate-700", !isError);
    status.classList.toggle("bg-slate-50", !isError);
  }

  function showForms() {
    forms.hidden = false;
    sessionPanel.hidden = true;
  }

  function showSession(user, appSession) {
    forms.hidden = true;
    sessionPanel.hidden = false;
    userEmail.textContent = user.email || "";
    userIdLabel.textContent = root.dataset.userIdLabel;
    userId.textContent = user.id || "";
    if (appSession) {
      userRole.textContent = appSession.role === "sensei"
        ? root.dataset.roleSensei
        : root.dataset.roleStudent;
      dashboardLink.href = appSession.redirect_url || "/dashboard";
      dashboardLink.hidden = false;
    } else {
      userRole.textContent = "";
      dashboardLink.hidden = true;
    }
  }

  function showMode(mode) {
    const signingUp = mode === "signup";
    signupForm.hidden = !signingUp;
    signinForm.hidden = signingUp;
    signupTab.setAttribute("aria-pressed", String(signingUp));
    signinTab.setAttribute("aria-pressed", String(!signingUp));
    signupTab.classList.toggle("bg-indigo-50", signingUp);
    signupTab.classList.toggle("text-indigo-700", signingUp);
    signinTab.classList.toggle("bg-indigo-50", !signingUp);
    signinTab.classList.toggle("text-indigo-700", !signingUp);
  }

  if (!root.dataset.authBaseUrl) {
    showStatus(root.dataset.missingConfig, true);
  } else {
    const auth = createAuthClient(root.dataset.authBaseUrl);

    async function readCurrentUser() {
      const { data, error } = await auth.getSession();
      if (error) {
        showStatus(error.message || root.dataset.sessionError, true);
        showForms();
        return null;
      }

      const user = data?.user;
      const token = data?.session?.token;
      if (!user || !token) {
        showForms();
        return null;
      }

      const response = await fetch("/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: token }),
      });
      if (!response.ok) {
        showSession(user, null);
        showStatus(root.dataset.sessionError, true);
        return null;
      }

      const appSession = await response.json();
      showSession(user, appSession);
      return appSession;
    }

    function redirectAfterLogin(appSession) {
      const returnTo = root.dataset.returnTo;
      const destination = returnTo.startsWith("/") && !returnTo.startsWith("//")
        ? returnTo
        : appSession.redirect_url || "/dashboard";
      window.location.assign(destination);
    }

    async function submitCredentials(form, operation) {
      const button = form.querySelector('button[type="submit"]');
      const label = button.textContent;
      button.disabled = true;
      button.textContent = operation === "signUp" ? root.dataset.signingUp : root.dataset.signingIn;
      showStatus("");

      try {
        const values = Object.fromEntries(new FormData(form));
        const result = operation === "signUp"
          ? await auth.signUp.email(values)
          : await auth.signIn.email(values);

        if (result.error) {
          showStatus(result.error.message || root.dataset.genericError, true);
          return;
        }

        const appSession = await readCurrentUser();
        if (appSession) {
          redirectAfterLogin(appSession);
        } else if (operation === "signUp") {
          showStatus(root.dataset.verificationPending);
        } else {
          showStatus(root.dataset.sessionError, true);
        }
      } catch (error) {
        showStatus(error?.message || root.dataset.genericError, true);
      } finally {
        button.disabled = false;
        button.textContent = label;
      }
    }

    signupTab.addEventListener("click", () => showMode("signup"));
    signinTab.addEventListener("click", () => showMode("signin"));
    signupForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void submitCredentials(signupForm, "signUp");
    });
    signinForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void submitCredentials(signinForm, "signIn");
    });
    signoutButton.addEventListener("click", async () => {
      signoutButton.disabled = true;
      try {
        let providerError = null;
        try {
          const result = await auth.signOut();
          providerError = result.error;
        } catch (error) {
          providerError = error;
        }
        const response = await fetch("/auth/logout", { method: "POST" });
        if (!response.ok) {
          throw new Error(root.dataset.genericError);
        }
        showForms();
        if (providerError) {
          showStatus(providerError.message || root.dataset.genericError, true);
          return;
        }
        showStatus(root.dataset.signedOut);
      } catch (error) {
        showStatus(error?.message || root.dataset.genericError, true);
      } finally {
        signoutButton.disabled = false;
      }
    });

    showMode("signup");
    void readCurrentUser()
      .then((appSession) => {
        if (appSession && root.dataset.refresh === "true") {
          redirectAfterLogin(appSession);
        }
      })
      .catch((error) => {
        showForms();
        showStatus(error?.message || root.dataset.sessionError, true);
      });
  }
}
