import { createAuthClient } from "@neon/auth";

const root = document.getElementById("auth-root");
const accountRoot = document.getElementById("account-root");

if (accountRoot && accountRoot.dataset.authBaseUrl) {
  const logoutForm = document.getElementById("account-logout-form");
  const logoutButton = logoutForm.querySelector('button[type="submit"]');
  const accountStatus = document.getElementById("account-status");
  const auth = createAuthClient(accountRoot.dataset.authBaseUrl);

  logoutForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    logoutButton.disabled = true;

    let providerError = null;
    try {
      const result = await auth.signOut();
      providerError = result.error;
    } catch (error) {
      providerError = error;
    }

    try {
      const response = await fetch(logoutForm.action, { method: "POST" });
      if (!response.ok) {
        throw new Error(accountRoot.dataset.genericError);
      }
      if (providerError) {
        accountStatus.textContent = providerError.message || accountRoot.dataset.sessionError;
        accountStatus.hidden = false;
        return;
      }
      window.location.assign("/");
    } catch (error) {
      accountStatus.textContent = error?.message || accountRoot.dataset.genericError;
      accountStatus.hidden = false;
    } finally {
      logoutButton.disabled = false;
    }
  });
}

if (root) {
  const status = document.getElementById("auth-status");
  const forms = document.getElementById("auth-forms");
  const signupForm = document.getElementById("signup-form");
  const signinForm = document.getElementById("signin-form");
  const verificationPanel = document.getElementById("verification-panel");
  const verificationForm = document.getElementById("verification-form");
  const verificationEmail = verificationForm.querySelector('input[name="email"]');
  const verificationCode = verificationForm.querySelector('input[name="otp"]');
  const resendVerificationButton = document.getElementById("resend-verification");
  const backToAuthButton = document.getElementById("back-to-auth");
  const openVerificationButton = document.getElementById("open-verification");
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
    verificationPanel.hidden = true;
  }

  function showVerification(email) {
    forms.hidden = true;
    verificationPanel.hidden = false;
    verificationEmail.value = email;
    verificationCode.value = "";
    (email ? verificationCode : verificationEmail).focus();
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
        showStatus("");
        showForms();
        return null;
      }

      const response = await fetch("/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: token }),
      });
      if (!response.ok) {
        showForms();
        showStatus(root.dataset.sessionError, true);
        return null;
      }

      return await response.json();
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

        if (operation === "signUp" && result.data?.user?.emailVerified === false) {
          showVerification(values.email);
          showStatus(root.dataset.verificationPending);
          return;
        }

        const appSession = await readCurrentUser();
        if (appSession) {
          redirectAfterLogin(appSession);
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
    verificationForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = verificationForm.querySelector('button[type="submit"]');
      const label = button.textContent;
      button.disabled = true;
      button.textContent = root.dataset.verifying;
      showStatus("");

      try {
        const result = await auth.emailOtp.verifyEmail({
          email: verificationEmail.value.trim(),
          otp: verificationCode.value.trim(),
        });
        if (result.error) {
          showStatus(result.error.message || root.dataset.genericError, true);
          return;
        }

        if (result.data?.session) {
          const appSession = await readCurrentUser();
          if (appSession) {
            redirectAfterLogin(appSession);
          }
          return;
        }

        showForms();
        showMode("signin");
        showStatus(root.dataset.verificationSuccess);
      } catch (error) {
        showStatus(error?.message || root.dataset.genericError, true);
      } finally {
        button.disabled = false;
        button.textContent = label;
      }
    });
    resendVerificationButton.addEventListener("click", async () => {
      resendVerificationButton.disabled = true;
      const label = resendVerificationButton.textContent;
      resendVerificationButton.textContent = root.dataset.resendingCode;
      showStatus("");

      try {
        const { error } = await auth.sendVerificationEmail({
          email: verificationEmail.value.trim(),
          callbackURL: window.location.origin,
        });
        if (error) {
          showStatus(error.message || root.dataset.genericError, true);
          return;
        }
        showStatus(root.dataset.verificationPending);
      } catch (error) {
        showStatus(error?.message || root.dataset.genericError, true);
      } finally {
        resendVerificationButton.disabled = false;
        resendVerificationButton.textContent = label;
      }
    });
    backToAuthButton.addEventListener("click", () => {
      showForms();
      showMode("signup");
      showStatus("");
    });
    openVerificationButton.addEventListener("click", () => {
      showVerification(signupForm.elements.email.value.trim());
      showStatus("");
    });
    showMode("signup");
    void readCurrentUser()
      .then((appSession) => {
        if (appSession) {
          if (root.dataset.returnTo.startsWith("/") && !root.dataset.returnTo.startsWith("//")) {
            redirectAfterLogin(appSession);
          } else {
            window.location.assign("/account");
          }
        }
      })
      .catch((error) => {
        showForms();
        showStatus(error?.message || root.dataset.sessionError, true);
      });
  }
}
